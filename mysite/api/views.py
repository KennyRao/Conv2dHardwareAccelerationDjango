# mysite/api/views.py
from __future__ import annotations

import base64
import io
import os
import time
import uuid
import shutil
from pathlib import Path

from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from PIL import Image

from .jobutils import (
    enqueue_filter_job,
    wait_for_file,
    run_scipy_filter_locally,
    read_time,
    cleanup,
)

BASE_DIR = Path(__file__).resolve().parent


# --------------------------------------------------------------------------- #
# Simple connectivity check
# --------------------------------------------------------------------------- #
class TestAPIView(APIView):
    def get(self, request):
        return Response({"message": "Working fine!"})


# --------------------------------------------------------------------------- #
# Demo *HTML* helpers (optional)
# --------------------------------------------------------------------------- #
def grayscale_test_view(request):
    return render(request, "grayscale_post_test.html")


def filter_test_view(request):
    return render(request, "filter_post_test.html")


# --------------------------------------------------------------------------- #
# Grayscale REST endpoint
# --------------------------------------------------------------------------- #
class GrayscaleAPIView(APIView):
    parser_classes = (MultiPartParser, FormParser)

    def get(self, request):
        """Return a static demo image converted to grayscale (software path)."""
        image_path = BASE_DIR / "test_img" / "input.jpg"
        img = Image.open(image_path).convert("L")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        buf.seek(0)
        return FileResponse(buf, content_type="image/jpeg")

    def post(self, request):
        uploaded_file = request.FILES.get("image")
        if not uploaded_file:
            return Response({"error": "No image uploaded"}, status=400)

        # ------------------------------------------------------------------- #
        # Create job folder & hand off to FPGA worker
        # ------------------------------------------------------------------- #
        job_id = f"job_{uuid.uuid4().hex}"
        job_path = BASE_DIR / "jobs" / job_id
        job_path.mkdir(parents=True, exist_ok=True)

        (job_path / "kernel.txt").write_text("grayscale")
        in_path = job_path / "in.jpg"
        with open(in_path, "wb") as out:
            for chunk in uploaded_file.chunks():
                out.write(chunk)

        done_path = job_path / "done.txt"
        out_jpg = job_path / "out.jpg"

        try:
            wait_for_file(done_path)
            img_bytes = out_jpg.read_bytes()
            return HttpResponse(img_bytes, content_type="image/jpeg")
        except TimeoutError:
            return JsonResponse({"error": "Timeout or processing failed"}, status=504)
        finally:
            cleanup(job_path)


# --------------------------------------------------------------------------- #
# 3×3 Filter REST endpoint
# --------------------------------------------------------------------------- #
class FilterAPIView(APIView):
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request):
        file = request.FILES.get("image")
        if file is None:
            return Response({"error": "No image"}, status=400)

        raw_coeffs = request.data.get("filter", "").strip()
        coeffs = list(map(int, raw_coeffs.split())) if raw_coeffs else []
        if coeffs and len(coeffs) != 9:
            return Response({"error": "Need 9 integers"}, status=400)

        try:
            factor = int(request.data.get("factor", 1))
        except ValueError:
            return Response({"error": "Factor must be int"}, status=400)

        # -------------------------------------------------------------- #
        # Hand off to FPGA worker
        # -------------------------------------------------------------- #
        job_id, job_path, out_path, done_path = enqueue_filter_job(file, coeffs, factor)

        try:
            wait_for_file(done_path)
        except TimeoutError:
            cleanup(job_path)
            return Response({"error": "Hardware timeout"}, status=504)

        # -------------------------------------------------------------- #
        # Assemble response JSON
        # -------------------------------------------------------------- #
        hw_b64 = base64.b64encode(out_path.read_bytes()).decode()
        resp = {
            "hw_image": hw_b64,
            "hw_time": read_time(job_path, "hw_time.txt"),
        }

        if "use_scipy" in request.POST:
            sw_b64, sw_time = run_scipy_filter_locally(file, coeffs, factor)
            resp.update({"sw_image": sw_b64, "sw_time": f"{sw_time:.4f} s"})

        cleanup(job_path)
        return Response(resp, status=200)
