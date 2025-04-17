# mysite/api/views.py
from __future__ import annotations
import os
import uuid
import shutil
import base64, io, time
from pathlib import Path

from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from PIL import Image

from .jobutils import (
    enqueue_filter_job, enqueue_grayscale_job,
    wait_for_file, run_scipy_filter, run_scipy_gray,
    read_time, list_history, trim_history,
)

BASE_DIR = Path(__file__).resolve().parent
OK_3X3 = lambda lst: len(lst) == 9


# --------------------------------------------------------------------------- #
# Simple connectivity check
# --------------------------------------------------------------------------- #
class TestAPIView(APIView):
    def get(self, request):
        return Response({"message": "Working fine!"})


# --------------------------------------------------------------------------- #
# Tests (not for final presentation)
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

    def post(self, request):
        img = request.FILES.get("image")
        if not img:
            return Response({"error": "No image uploaded"}, status=400)

        job = enqueue_grayscale_job(img)
        try:
            wait_for_file(job / "done.txt")
        except TimeoutError:
            return Response({"error": "Hardware timeout"}, status=504)

        # Assemble JSON (hw + optional sw)
        hw_b64 = base64.b64encode((job / "out.jpg").read_bytes()).decode()
        resp = {
            "hw_image": hw_b64,
            "hw_time": read_time(job),
        }
        if "use_scipy" in request.POST:
            sw_b64, sw_t = run_scipy_gray(img)
            resp.update({"sw_image": sw_b64, "sw_time": f"{sw_t*1e3:.2f} ms"})

        trim_history()                      # keep only latest 10
        return Response(resp)


# --------------------------------------------------------------------------- #
# 3×3 Filter REST endpoint
# --------------------------------------------------------------------------- #
class FilterAPIView(APIView):
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request):
        img = request.FILES.get("image")
        raw = request.data.get("filter", "").strip()
        coeffs = list(map(int, raw.split())) if raw else []
        factor = int(request.data.get("factor", 1) or 1)

        # Validate
        if not img:
            return Response({"error": "No image"}, status=400)
        if not OK_3X3(coeffs):
            return Response({"error": "Kernel must have 9 integers"}, status=400)
        if factor <= 0:
            return Response({"error": "Factor must be positive"}, status=400)

        job = enqueue_filter_job(img, coeffs, factor)
        try:
            wait_for_file(job / "done.txt")
        except TimeoutError:
            return Response({"error": "Hardware timeout"}, status=504)

        hw_b64 = base64.b64encode((job / "out.jpg").read_bytes()).decode()
        resp = {
            "hw_image": hw_b64,
            "hw_time": read_time(job),
        }
        if "use_scipy" in request.POST:
            sw_b64, sw = run_scipy_filter(img, coeffs, factor)
            resp.update({"sw_image": sw_b64, "sw_time": f"{sw*1e3:.2f} ms"})

        trim_history()
        return Response(resp)


# --------------------------------------------------------------------------- #
# Job history
# --------------------------------------------------------------------------- #
class HistoryAPIView(APIView):
    def get(self, _):
        return Response(list_history())

    def delete(self, _):
        # wipe all completed jobs
        for j in (BASE_DIR / "jobs").iterdir():
            if (j / "done.txt").exists():
                from shutil import rmtree
                rmtree(j, ignore_errors=True)
        return Response({"status": "cleared"}, status=204)
