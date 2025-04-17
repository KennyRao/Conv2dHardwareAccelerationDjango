# mysite/api/jobutils.py
"""
Utility helpers for enqueueing jobs and polling worker results.
All functions are intentionally short & self‑contained.
"""
from pathlib import Path
import os, time, uuid, shutil, base64
import numpy as np
from PIL import Image
from scipy.signal import convolve2d

JOBS_ROOT = Path(__file__).resolve().parent / "jobs"
JOBS_ROOT.mkdir(exist_ok=True)

def enqueue_filter_job(uploaded_file, coeffs, factor):
    """Create a unique job folder and write all control files."""
    job_id = f"job_{uuid.uuid4().hex}"
    job = JOBS_ROOT / job_id
    job.mkdir()

    # save image
    in_path = job / "in.jpg"
    Image.open(uploaded_file).save(in_path)

    # control files for worker.py
    (job / "kernel.txt").write_text("filter")
    (job / "factor.txt").write_text(str(factor))
    if coeffs:
        (job / "filter.txt").write_text(" ".join(map(str, coeffs)))

    return job_id, job, job / "out.jpg", job / "done.txt"

def wait_for_file(path: Path, timeout=30):
    """Block until *path* exists or raise TimeoutError."""
    start = time.time()
    while not path.exists():
        if time.time() - start > timeout:
            raise TimeoutError(f"{path} not written after {timeout}s")
        time.sleep(0.5)

def run_scipy_filter_locally(uploaded_file, coeffs, factor):
    """Pure‑software reference using SciPy."""
    img_rgb = np.array(Image.open(uploaded_file).convert("RGB"))
    k = np.array(coeffs, dtype=np.int32).reshape(3, 3) if coeffs else np.eye(3)
    k = k / factor

    t0 = time.perf_counter()
    out = np.zeros_like(img_rgb)
    for c in range(3):
        out[..., c] = convolve2d(img_rgb[..., c], k, mode="same",
                                 boundary="symm")  # reflect
    sw_time = time.perf_counter() - t0

    buf = io.BytesIO()
    Image.fromarray(out.clip(0, 255).astype(np.uint8)).save(buf, format="JPEG")
    sw_b64 = base64.b64encode(buf.getvalue()).decode()
    return sw_b64, sw_time

def read_time(job: Path, fname: str):
    try:
        return (job / fname).read_text().strip()
    except FileNotFoundError:
        return "N/A"

def cleanup(job: Path):
    """Delete the entire job folder tree (shutil docs)"""
    try:
        shutil.rmtree(job)
    except Exception as exc:
        print("Cleanup warning:", exc)
