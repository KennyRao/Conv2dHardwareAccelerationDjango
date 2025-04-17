# mysite/api/jobutils.py
"""
Utility helpers for enqueueing jobs and polling worker results.
All functions are intentionally short & self‑contained.
"""
from __future__ import annotations

import io
import os
import shutil
import time
import uuid
import base64
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.signal import convolve2d

JOBS_ROOT = Path(__file__).resolve().parent / "jobs"
JOBS_ROOT.mkdir(exist_ok=True)


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _save_uploaded(uploaded_file, dst: Path) -> None:
    """Stream‑save a Django *UploadedFile* to *dst* without reading it all
    into memory, then rewind the file so callers may reuse it."""
    with open(dst, "wb") as f:
        for chunk in uploaded_file.chunks():
            f.write(chunk)
    try:
        uploaded_file.seek(0)            # rewind for Pillow / further use
    except Exception:
        pass


def wait_for_file(path: Path, timeout: int = 45) -> None:
    """Block until *path* exists or raise *TimeoutError*."""
    start = time.perf_counter()
    while not path.exists():
        if time.perf_counter() - start > timeout:
            raise TimeoutError(f"{path} not written after {timeout}s")
        time.sleep(0.4)


def read_time(job: Path, fname: str) -> str:
    try:
        return (job / fname).read_text().strip()
    except FileNotFoundError:
        return "N/A"


def cleanup(job: Path) -> None:
    """Delete the entire job folder tree (best‑effort)."""
    try:
        shutil.rmtree(job)
    except Exception as exc:
        print("Cleanup warning:", exc)


# --------------------------------------------------------------------------- #
# Job creation helpers
# --------------------------------------------------------------------------- #
def enqueue_filter_job(uploaded_file, coeffs, factor: int):
    """Create a unique job folder and write all control files for *filter*."""
    job_id = f"job_{uuid.uuid4().hex}"
    job = JOBS_ROOT / job_id
    job.mkdir()

    # save the raw RGB image exactly as uploaded
    in_path = job / "in.jpg"
    _save_uploaded(uploaded_file, in_path)

    # meta files consumed by the FPGA worker
    (job / "kernel.txt").write_text("filter")
    (job / "factor.txt").write_text(str(factor))
    if coeffs:
        (job / "filter.txt").write_text(" ".join(map(str, coeffs)))

    return job_id, job, job / "out.jpg", job / "done.txt"


# --------------------------------------------------------------------------- #
# Optional software reference (SciPy convolution)
# --------------------------------------------------------------------------- #
def run_scipy_filter_locally(uploaded_file, coeffs, factor: int):
    """Pure‑software reference using SciPy (reflect padding)."""
    img_rgb = np.array(Image.open(uploaded_file).convert("RGB"))
    k = (
        np.array(coeffs, dtype=np.int32).reshape(3, 3)
        if coeffs
        else np.eye(3)
    ) / factor

    t0 = time.perf_counter()
    out = np.zeros_like(img_rgb)
    for c in range(3):
        out[..., c] = convolve2d(img_rgb[..., c], k, mode="same", boundary="symm")
    sw_time = time.perf_counter() - t0

    buf = io.BytesIO()
    Image.fromarray(out.clip(0, 255).astype(np.uint8)).save(buf, format="JPEG")
    sw_b64 = base64.b64encode(buf.getvalue()).decode()
    return sw_b64, sw_time
