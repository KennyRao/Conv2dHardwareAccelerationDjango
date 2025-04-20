# mysite/api/views.py
from __future__ import annotations
import base64, shutil, json
from pathlib import Path

from django.http import FileResponse, Http404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework import status

from .jobutils import (
    enqueue_grayscale_job, enqueue_filter_job,
    enqueue_video_grayscale_job, enqueue_video_filter_job,
    wait_for_file, run_scipy_gray, run_scipy_filter,
    read_time, list_history, trim_image_history, trim_video_history,
    JOBS_ROOT, MAX_VIDEO_BYTES, _encode
)

OK_3X3 = lambda lst: len(lst) == 9
QUEUED_TIMEOUT = 10  # seconds to wait before giving 202


# --------------------------------------------------------------------------- #
# Simple connectivity check
# --------------------------------------------------------------------------- #
class TestAPIView(APIView):
    def get(self, request):
        return Response({"message": "Working fine!"})


# --------------------------------------------------------------------------- #
# Helper - return a standard queued response
# --------------------------------------------------------------------------- #
def _queued(job) -> Response:
    return Response(
        {
            "job_id": job.name,
            "queued": True,
            "message": "Job queued - check progress in the History tab."
        },
        status=status.HTTP_202_ACCEPTED,
    )


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
            wait_for_file(job / "done.txt", timeout=QUEUED_TIMEOUT)
        except TimeoutError:               # still queued / running
            return _queued(job)

        hw_b64 = base64.b64encode((job / "out.jpg").read_bytes()).decode()
        resp = {
            "hw_image": hw_b64,
            "hw_time": read_time(job),
        }
        if "use_scipy" in request.POST:
            sw_b64, sw_t = run_scipy_gray(img)
            resp.update({"sw_image": sw_b64, "sw_time": f"{sw_t*1e3:.2f} ms"})

        trim_image_history()
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
            wait_for_file(job / "done.txt", timeout=QUEUED_TIMEOUT)
        except TimeoutError:
            return _queued(job)

        hw_b64 = base64.b64encode((job / "out.jpg").read_bytes()).decode()
        resp = {
            "hw_image": hw_b64,
            "hw_time": read_time(job),
        }
        if "use_scipy" in request.POST:
            sw_b64, sw_t = run_scipy_filter(img, coeffs, factor)
            resp.update({"sw_image": sw_b64, "sw_time": f"{sw_t*1e3:.2f} ms"})

        trim_image_history()
        return Response(resp)


# --------------------------------------------------------------------------- #
# Video → Grayscale
# --------------------------------------------------------------------------- #
class VideoGrayscaleAPIView(APIView):
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request):
        vid = request.FILES.get("video")
        if not vid:
            return Response({"error": "No video"}, status=400)
        if vid.size > MAX_VIDEO_BYTES:
            return Response({"error": "Video > 1 GiB - please compress first"}, 413)

        job = enqueue_video_grayscale_job(vid)
        return _queued(job)  # always queue - videos are long


# --------------------------------------------------------------------------- #
# Video → Filter
# --------------------------------------------------------------------------- #
class VideoFilterAPIView(APIView):
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request):
        vid = request.FILES.get("video")
        raw = request.data.get("filter", "").strip()
        coeffs = list(map(int, raw.split())) if raw else []
        factor = int(request.data.get("factor", 1) or 1)

        if not vid:
            return Response({"error": "No video"}, status=400)
        if vid.size > MAX_VIDEO_BYTES:
            return Response({"error": "Video > 1 GiB - please compress first"}, 413)
        if not OK_3X3(coeffs):
            return Response({"error": "Kernel must have 9 integers"}, status=400)
        if factor <= 0:
            return Response({"error": "Factor must be positive"}, status=400)

        job = enqueue_video_filter_job(vid, coeffs, factor)
        return _queued(job)  # always queue - videos are long


# --------------------------------------------------------------------------- #
# Video result download
# --------------------------------------------------------------------------- #
class VideoResultAPIView(APIView):
    def get(self, _, job_id: str):
        video_path = JOBS_ROOT / job_id / "out.mp4"
        if not video_path.exists():
            raise Http404
        return FileResponse(open(video_path, "rb"),
                            content_type="video/mp4",
                            as_attachment=True,   # force download
                            filename="result.mp4")


# --------------------------------------------------------------------------- #
# Job history
# --------------------------------------------------------------------------- #
class HistoryAPIView(APIView):
    def get(self, _):
        return Response(list_history())

    def delete(self, _):
        # wipe all completed jobs
        removed = []
        for j in JOBS_ROOT.iterdir():
            shutil.rmtree(j, ignore_errors=True)
            removed.append(j.name)
        return Response({"deleted": removed}, status=204)
