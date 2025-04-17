# mysite/api/jobutils.py
"""
Utility helpers for enqueueing jobs, polling results and maintaining history.
"""
from __future__ import annotations
import io, os, shutil, time, uuid, base64, json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.signal import convolve2d

JOBS_ROOT = Path(__file__).resolve().parent / "jobs"
JOBS_ROOT.mkdir(exist_ok=True)
HISTORY_LIMIT = 10  # keep at most N finished jobs


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _save_uploaded(uploaded_file, dst: Path) -> None:
    """Stream‑save a Django *UploadedFile*."""
    with dst.open("wb") as f:
        for chunk in uploaded_file.chunks():
            f.write(chunk)
    try:
        uploaded_file.seek(0)
    except Exception:
        pass


def wait_for_file(path: Path, timeout: int = 45) -> None:
    """Block until *path* exists or raise *TimeoutError*."""
    start = time.perf_counter()
    while not path.exists():
        if time.perf_counter() - start > timeout:
            raise TimeoutError(f"{path} not written after {timeout}s")
        time.sleep(0.4)


def read_time(job: Path) -> str:
    try:
        return (job / "hw_time.txt").read_text().strip()
    except FileNotFoundError:
        return "N/A"


# --------------------------------------------------------------------------- #
# Job creation helpers
# --------------------------------------------------------------------------- #
def _create_job(prefix: str) -> Path:
    job_id = f"{prefix}_{uuid.uuid4().hex}"
    job = JOBS_ROOT / job_id
    job.mkdir()
    return job


def enqueue_filter_job(uploaded_file, coeffs, factor: int) -> Path:
    job = _create_job("job")
    _save_uploaded(uploaded_file, job / "in.jpg")
    (job / "kernel.txt").write_text("filter")
    (job / "factor.txt").write_text(str(factor))
    (job / "filter.txt").write_text(" ".join(map(str, coeffs)))
    return job


def enqueue_grayscale_job(uploaded_file) -> Path:
    job = _create_job("job")
    _save_uploaded(uploaded_file, job / "in.jpg")
    (job / "kernel.txt").write_text("grayscale")
    return job


# --------------------------------------------------------------------------- #
# Optional software reference
# --------------------------------------------------------------------------- #
def _run_conv(img_rgb, k) -> np.ndarray:
    out = np.zeros_like(img_rgb)
    for c in range(3):
        out[..., c] = convolve2d(img_rgb[..., c], k, mode="same", boundary="symm")
    return out.clip(0, 255).astype(np.uint8)


def run_scipy_filter(img_file, coeffs, factor: int):
    img_rgb = np.array(Image.open(img_file).convert("RGB"))
    k = np.array(coeffs, dtype=np.int32).reshape(3, 3) / factor
    t0 = time.perf_counter()
    out = _run_conv(img_rgb, k)
    return _encode(out), time.perf_counter() - t0


def run_scipy_gray(img_file):
    img_rgb = np.array(Image.open(img_file).convert("RGB"))
    # ITU BT.601 luma weights
    k = np.array([[0.299, 0.587, 0.114]])
    gray = (img_rgb @ k.T).astype(np.uint8)
    img = np.repeat(gray, 3, axis=2)          # 3‑channel for fair comparison
    buf, t0 = io.BytesIO(), time.perf_counter()
    Image.fromarray(img).save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode(), time.perf_counter() - t0


# --------------------------------------------------------------------------- #
# History helpers
# --------------------------------------------------------------------------- #
def _encode(arr: np.ndarray) -> str:
    """JPEG→base64 helper."""
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode()


def list_history() -> list[dict]:
    jobs = sorted([p for p in JOBS_ROOT.iterdir() if (p / "done.txt").exists()],
                  key=lambda p: p.stat().st_mtime, reverse=True)[:HISTORY_LIMIT]
    out: list[dict] = []
    for j in jobs:
        kind = (j / "kernel.txt").read_text().strip()
        meta = {
            "id": j.name,
            "kind": kind,
            "time": read_time(j),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(j.stat().st_mtime)),
            "image": _encode(np.array(Image.open(j / "out.jpg"))),
        }
        if kind == "filter":
            meta["factor"] = (j / "factor.txt").read_text().strip()
            meta["kernel"] = (j / "filter.txt").read_text().strip()
        out.append(meta)
    return out


def trim_history(limit: int = HISTORY_LIMIT) -> None:
    jobs = sorted([p for p in JOBS_ROOT.iterdir() if (p / "done.txt").exists()],
                  key=lambda p: p.stat().st_mtime, reverse=True)
    for p in jobs[limit:]:
        shutil.rmtree(p, ignore_errors=True)
