# mysite/api/views.py
from __future__ import annotations
import base64, shutil
from pathlib import Path
from typing import Callable

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
    JOBS_ROOT, MAX_VIDEO_BYTES
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
# Helper - return a standard queued response
# --------------------------------------------------------------------------- #
def _queued(job, msg: str = "Job queued - please check progress in the History tab.") -> Response:
    return Response(
        {
            "job_id": job.name,
            "queued": True,
            "message": msg
        },
        status=status.HTTP_202_ACCEPTED,
    )

# --------------------------------------------------------------------------- #
# Helper - check is there any unfinished job created before
# --------------------------------------------------------------------------- #
def _has_pending_before(me: Path) -> bool:
    for p in JOBS_ROOT.iterdir():
        if p == me:
            continue
        if (p / "done.txt").exists() or (p / "error.txt").exists():
            continue           # finished jobs don't count
        if p.stat().st_mtime < me.stat().st_mtime:
            return True
    return False


# --------------------------------------------------------------------------- #
# Helper - handle “quick-if-idle else queue” logic (images only)
# --------------------------------------------------------------------------- #
def _handle_image_request(enqueue_func: Callable[[], Path], do_software: Callable[[], tuple[str, str]] | None = None) -> Response:
    job = enqueue_func()

    # If another job is already running/queued, respond immediately
    if _has_pending_before(job):
        return _queued(job)

    # Otherwise wait a bit - ideal case for single-image workflows
    try:
        wait_for_file(job / "done.txt", timeout=QUEUED_TIMEOUT)
    except TimeoutError:
        return _queued(job, "Job is taking longer than expected - please check progress in the History tab.")

    # Finished quickly - return hardware (and optional software) image
    hw_b64 = base64.b64encode((job / "out.jpg").read_bytes()).decode()
    resp   = {"hw_image": hw_b64, "hw_time": read_time(job)}
    if do_software is not None:
        sw_b64, sw_time = do_software()
        resp.update({"sw_image": sw_b64, "sw_time": f"{sw_time*1e3:.2f} ms"})
    trim_image_history()
    return Response(resp)


# --------------------------------------------------------------------------- #
# Grayscale REST endpoint
# --------------------------------------------------------------------------- #
class GrayscaleAPIView(APIView):
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request):
        img = request.FILES.get("image")
        if not img:
            return Response({"error": "No image uploaded"}, status=400)

        return _handle_image_request(
            enqueue_func=lambda: enqueue_grayscale_job(img),
            do_software=(lambda: run_scipy_gray(img)) if "use_scipy" in request.POST else None,
        )


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

        return _handle_image_request(
            enqueue_func=lambda: enqueue_filter_job(img, coeffs, factor),
            do_software=(lambda: run_scipy_filter(img, coeffs, factor)) if "use_scipy" in request.POST else None,
        )


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
        trim_video_history()
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
        trim_video_history()
        return _queued(job)  # always queue - videos are long


# --------------------------------------------------------------------------- #
# Results download
# --------------------------------------------------------------------------- #
class ImageResultAPIView(APIView):
    """
    Download finished image (out.jpg) for a job.
    """
    def get(self, _, job_id: str):
        img_path: Path = JOBS_ROOT / job_id / "out.jpg"
        if not img_path.exists():
            raise Http404
        return FileResponse(open(img_path, "rb"),
                            content_type="image/jpeg",
                            as_attachment=True,
                            filename="result.jpg")

class VideoResultAPIView(APIView):
    def get(self, _, job_id: str):
        video_path = JOBS_ROOT / job_id / "out.mp4"
        if not video_path.exists():
            raise Http404
        return FileResponse(open(video_path, "rb"),
                            content_type="video/mp4",
                            as_attachment=True,
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
