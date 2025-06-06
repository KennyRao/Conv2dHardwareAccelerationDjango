# mysite/api/jobutils.py
"""
Utility helpers for enqueueing jobs, polling results and maintaining history.
"""

from __future__ import annotations
import io, json, shutil, time, uuid, base64
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.signal import convolve2d

# --------------------------------------------------------------------------- #
# Globals & limits
# --------------------------------------------------------------------------- #
JOBS_ROOT            = Path(__file__).resolve().parent / "jobs"
JOBS_ROOT.mkdir(exist_ok=True)
MAX_WIDTH            = 1920
MAX_HEIGHT           = 1080
MAX_VIDEO_BYTES      = 1_073_741_824  # 1 GiB
HISTORY_LIMIT_IMG    = 10
HISTORY_LIMIT_VIDEO  = 1
STATUS_FILE          = "status.json"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def save_uploaded(uploaded_file, dst: Path) -> None:
    """Stream-save a Django *UploadedFile*."""
    with dst.open("wb") as f:
        for chunk in uploaded_file.chunks():
            f.write(chunk)
    try:
        uploaded_file.seek(0)
    except Exception:
        pass

def resize_image_if_needed(path: Path) -> None:
    with Image.open(path) as im:
        w, h = im.size
        if w <= MAX_WIDTH and h <= MAX_HEIGHT:
            return
        im.thumbnail((MAX_WIDTH, MAX_HEIGHT), Image.LANCZOS)
        im.save(path, format="JPEG", quality=100)

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

def _encode(arr: np.ndarray) -> str:
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode()


# --------------------------------------------------------------------------- #
# Job creation helpers
# --------------------------------------------------------------------------- #
def create_job(prefix: str) -> Path:
    job_id = f"{prefix}_{uuid.uuid4().hex}"
    job = JOBS_ROOT / job_id
    job.mkdir()
    return job

def enqueue_grayscale_job(uploaded_file):
    job = create_job("job_img")
    save_uploaded(uploaded_file, job / "in.jpg")
    resize_image_if_needed(job / "in.jpg")
    (job / "kernel.txt").write_text("grayscale")
    return job

def enqueue_filter_job(uploaded_file, coeffs, factor: int):
    job = create_job("job_img")
    save_uploaded(uploaded_file, job / "in.jpg")
    resize_image_if_needed(job / "in.jpg")
    (job / "kernel.txt").write_text("filter")
    (job / "factor.txt").write_text(str(factor))
    (job / "filter.txt").write_text(" ".join(map(str, coeffs)))
    return job

def enqueue_video_grayscale_job(uploaded_file):
    if uploaded_file.size > MAX_VIDEO_BYTES:
        raise ValueError("Video exceeds 1 GiB limit")
    job = create_job("job_vid")
    save_uploaded(uploaded_file, job / "in.mp4")
    (job / "kernel.txt").write_text("grayscale_video")
    return job

def enqueue_video_filter_job(uploaded_file, coeffs, factor: int):
    if uploaded_file.size > MAX_VIDEO_BYTES:
        raise ValueError("Video exceeds 1 GiB limit")
    job = create_job("job_vid")
    save_uploaded(uploaded_file, job / "in.mp4")
    (job / "kernel.txt").write_text("filter_video")
    (job / "factor.txt").write_text(str(factor))
    (job / "filter.txt").write_text(" ".join(map(str, coeffs)))
    return job


# --------------------------------------------------------------------------- #
# Optional SciPy reference (images only)
# --------------------------------------------------------------------------- #
def run_conv2d(img_rgb, k):
    out = np.zeros_like(img_rgb)
    for c in range(3):
        out[..., c] = convolve2d(img_rgb[..., c], k, mode="same", boundary="symm")
    return out.clip(0, 255).astype(np.uint8)

def run_scipy_gray(img_file):
    img_rgb = np.array(Image.open(img_file).convert("RGB"))
    gray = (img_rgb @ np.array([[0.299, 0.587, 0.114]]).T).astype(np.uint8)
    img = np.repeat(gray, 3, axis=2)
    buf, t0 = io.BytesIO(), time.perf_counter()
    Image.fromarray(img).save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode(), time.perf_counter() - t0

def run_scipy_filter(img_file, coeffs, factor: int):
    img_rgb = np.array(Image.open(img_file).convert("RGB"))
    k = np.array(coeffs, dtype=np.int32).reshape(3, 3) / factor
    t0 = time.perf_counter()
    out = run_conv2d(img_rgb, k)
    return _encode(out), time.perf_counter() - t0


# --------------------------------------------------------------------------- #
# History helpers
# --------------------------------------------------------------------------- #
def read_status(job: Path) -> dict:
    try:
        return json.loads((job / STATUS_FILE).read_text())
    except Exception:
        return {}

def list_history() -> list[dict]:
    """Return image + video job list (newest first) including live status."""
    jobs = sorted(JOBS_ROOT.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)

    out: list[dict] = []
    for j in jobs:
        kind = (j / "kernel.txt").read_text().strip() if (j / "kernel.txt").exists() else "?"
        is_video = kind.endswith("_video")
        status = read_status(j) or {"stage": "queued"}
        stage = status.get("stage", "unknown")
        prog = status.get("progress", {})
        done, tot = prog.get("done", 0), prog.get("total", 0)
        pct = int(done / tot * 100) if tot else (100 if stage == "finished" else 0)

        meta = {
            "id": j.name,
            "kind": kind,
            "is_video": is_video,
            "status": stage,
            "progress": pct,
            "time": read_time(j),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(j.stat().st_mtime)),
        }

        # preview / download links
        if (j / "out.jpg").exists():
            meta["image"] = _encode(np.array(Image.open(j / "out.jpg")))
            meta["image_url"] = f"/api/image/result/{j.name}/"
        else:
            meta["image"] = ""

        if is_video:
            meta["video_url"] = f"/api/video/result/{j.name}/"

        if kind in ("filter", "filter_video") and (j / "filter.txt").exists():
            meta["factor"] = (j / "factor.txt").read_text().strip()
            meta["kernel"] = (j / "filter.txt").read_text().strip()

        out.append(meta)
    return out


def trim_image_history(limit: int = HISTORY_LIMIT_IMG):
    imgs = sorted([p for p in JOBS_ROOT.iterdir()
                   if p.name.startswith("job_img") and (p / "done.txt").exists()],
                  key=lambda p: p.stat().st_mtime, reverse=True)
    for p in imgs[limit:]:
        shutil.rmtree(p, ignore_errors=True)


def trim_video_history(limit: int = HISTORY_LIMIT_VIDEO):
    vids = sorted([p for p in JOBS_ROOT.iterdir()
                   if p.name.startswith("job_vid") and (p / "done.txt").exists()],
                  key=lambda p: p.stat().st_mtime, reverse=True)
    for p in vids[limit:]:
        shutil.rmtree(p, ignore_errors=True)
