# worker.py
"""
Background worker for FPGA image/video jobs.
Keeps per-job status in status.json so the front-end can poll progress.
Only **one** worker process should run on the PYNQ because DMA / overlay
resources are not thread-safe.  Jobs are processed strictly FIFO.
"""

from __future__ import annotations
import json, os, sys, time, traceback
from pathlib import Path
from typing import Literal, Optional

import cv2
import numpy as np
from PIL import Image
from pynq import Overlay, allocate, DefaultIP

# --------------------------------------------------------------------------- #
# Logging configuration
# --------------------------------------------------------------------------- #
import logging

_DEBUG = bool(int(os.getenv("WORKER_DEBUG", "0")))
logging.basicConfig(
    level=logging.DEBUG if _DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("worker")

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #
JOBS_DIR = Path("/home/xilinx/f_c_a_api/mysite/api/jobs")
MAX_W, MAX_H = 1920, 1080  # resize cap for large videos

STATUS_FILE = "status.json"
OVERLAY_PATHS = {
    "grayscale": "/home/xilinx/pynq/overlays/grayscale/grayscale.bit",
    "filter":    "/home/xilinx/pynq/overlays/filter/filter.bit",
}

# --------------------------------------------------------------------------- #
# FPGA custom driver
# --------------------------------------------------------------------------- #
class FilterKernel(DefaultIP):
    bindto = ["xilinx.com:hls:filter_kernel:1.0"]

    def __init__(self, desc):
        super().__init__(description=desc)
        rm = self.register_map
        self.width_addr  = rm.image_width.address
        self.height_addr = rm.image_height.address
        self.factor_addr = rm.kernel_factor.address
        self.kernel_addr = 0x40

    width  = property(lambda s: s.read(s.width_addr),
                      lambda s, v: s.write(s.width_addr, v))
    height = property(lambda s: s.read(s.height_addr),
                      lambda s, v: s.write(s.height_addr, v))
    factor = property(lambda s: s.read(s.factor_addr),
                      lambda s, v: s.write(s.factor_addr, v))

    @property
    def kernel(self):
        flat = [self.read(self.kernel_addr + 4*i) for i in range(9)]
        return np.array(flat, np.int32).reshape(3, 3)

    @kernel.setter
    def kernel(self, m):
        flat = np.array(m, np.int32).ravel()
        if flat.size != 9:
            raise ValueError("Kernel must be 3×3")
        for i, v in enumerate(flat):
            self.write(self.kernel_addr + 4*i, int(v))

# --------------------------------------------------------------------------- #
# Globals set by load_overlay()
# --------------------------------------------------------------------------- #
current_overlay = current_dma = current_ip = None   # FPGA objects
loaded_kernel  : Optional[str] = None              # "grayscale" | "filter"

# --------------------------------------------------------------------------- #
# Helper - job status I/O
# --------------------------------------------------------------------------- #
def _status_path(job: Path) -> Path:
    return job / STATUS_FILE

def write_status(job: Path,
                  stage: Literal[
                      "queued", "receiving", "kernel_loaded",
                      "processing", "merging",
                      "finished", "error"
                  ],
                  note: str | None = None,
                  progress: tuple[int, int] | None = None) -> None:
    data: dict[str, object] = {
        "stage": stage,
        "timestamp": time.time(),
    }
    if note is not None:
        data["note"] = note
    if progress is not None:
        done, total = progress
        data["progress"] = {"done": done, "total": total}
    tmp = _status_path(job).with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.rename(_status_path(job))

def _read_status(job: Path) -> dict:
    try:
        return json.loads(_status_path(job).read_text())
    except Exception:
        return {}

# --------------------------------------------------------------------------- #
# Overlay management
# --------------------------------------------------------------------------- #
def load_overlay(kind: str) -> None:
    """
    Load bitstream only when necessary.
    ``kind`` is one of "grayscale", "filter".
    """
    global current_overlay, current_ip, current_dma, loaded_kernel

    base = kind.removesuffix("_video")
    if loaded_kernel == base:
        log.debug("overlay %s already loaded", base)
        return

    bit = OVERLAY_PATHS[base]
    log.info("loading overlay: %s", bit)
    t0 = time.perf_counter()
    current_overlay = Overlay(bit)
    current_dma     = current_overlay.axi_dma_0
    current_ip      = (current_overlay.grayscale_kernel_0
                       if base == "grayscale" else current_overlay.filter_kernel_0)
    loaded_kernel  = base
    log.info("overlay ready (%.1f ms)", (time.perf_counter() - t0)*1e3)

# --------------------------------------------------------------------------- #
# Low‑level accelerator invocation
# --------------------------------------------------------------------------- #
def run_accelerator(rgb: np.ndarray, cfg_func) -> tuple[np.ndarray, float]:
    """
    Push one RGB frame through the accelerator.
    Returns (output_rgb, elapsed_ms).
    """
    comb = ((rgb[..., 0].astype(np.uint32) << 16) |
            (rgb[..., 1].astype(np.uint32) <<  8) |
             rgb[..., 2].astype(np.uint32))
    input_buffer  = allocate(comb.shape, dtype=np.uint32)
    output_buffer = allocate(comb.shape, dtype=np.uint32)
    input_buffer[:] = comb

    cfg_func(rgb)                       # setup IP registers
    current_ip.write(0x00, 1)          # ap_start

    t0 = time.perf_counter()
    current_dma.sendchannel.transfer(input_buffer)
    current_dma.recvchannel.transfer(output_buffer)
    current_dma.sendchannel.wait()
    current_dma.recvchannel.wait()
    time_elapsed = (time.perf_counter() - t0) * 1e3

    r = (output_buffer >> 16) & 0xFF
    g = (output_buffer >>  8) & 0xFF
    b =  output_buffer        & 0xFF
    rgb_output = np.stack((r, g, b), axis=-1).astype(np.uint8)

    input_buffer.freebuffer(); output_buffer.freebuffer()
    return rgb_output, time_elapsed

# --------------------------------------------------------------------------- #
# Register configuration helpers
# --------------------------------------------------------------------------- #
def cfg_grayscale(arr):
    h, w = arr.shape[:2]
    current_ip.write(0x10, w)
    current_ip.write(0x18, h)

def cfg_filter(arr, job: Path):
    h, w = arr.shape[:2]
    current_ip.height = h
    current_ip.width  = w
    current_ip.factor = int((job / "factor.txt").read_text())
    k = np.fromstring((job / "filter.txt").read_text(), sep=" ",
                      dtype=np.int32).reshape(3, 3)
    current_ip.kernel = k

# --------------------------------------------------------------------------- #
# Job executors
# --------------------------------------------------------------------------- #
def process_image(job: Path, kind: str) -> None:
    log.info("▶ IMAGE job %s (%s)", job.name, kind)
    load_overlay(kind)
    write_status(job, "kernel_loaded")

    img = np.array(Image.open(job / "in.jpg"))
    cfg = cfg_grayscale if kind == "grayscale" else lambda a: cfg_filter(a, job)

    write_status(job, "processing")
    out, t_ms = run_accelerator(img, cfg)

    Image.fromarray(out).save(job / "out.jpg")
    (job / "hw_time.txt").write_text(f"{t_ms:.2f} ms")
    write_status(job, "finished", progress=(1, 1))
    (job / "done.txt").write_text("done")
    log.info("✔ IMAGE job %s finished (%.2f ms)", job.name, t_ms)

def process_video(job: Path, kind: str) -> None:
    log.info("▶ VIDEO job %s (%s)", job.name, kind)
    load_overlay(kind)
    write_status(job, "kernel_loaded")

    cap = cv2.VideoCapture(str(job / "in.mp4"))
    if not cap.isOpened():
        raise RuntimeError("OpenCV failed to open video")

    fps  = cap.get(cv2.CAP_PROP_FPS) or 25.0
    tot  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    w    = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h    = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    scale = max(w/MAX_W, h/MAX_H, 1.0)
    ow, oh = int(w/scale), int(h/scale)

    vw = cv2.VideoWriter(str(job / "out.mp4"),
                         cv2.VideoWriter_fourcc(*"mp4v"), fps, (ow, oh))
    cfg = cfg_grayscale if kind == "grayscale_video" else lambda a: cfg_filter(a, job)

    first_snap = None
    done, total_ms = 0, 0.0
    write_status(job, "processing", progress=(0, tot))
    while True:
        ok, frm = cap.read()
        if not ok:
            break
        if scale > 1.0:
            frm = cv2.resize(frm, (ow, oh), cv2.INTER_AREA)
        rgb = cv2.cvtColor(frm, cv2.COLOR_BGR2RGB)
        out, t_ms = run_accelerator(rgb, cfg)
        total_ms += t_ms

        if first_snap is None:
            first_snap = out.copy()
        vw.write(cv2.cvtColor(out, cv2.COLOR_RGB2BGR))

        done += 1
        # update every 5 frames to limit disk I/O
        if done % 5 == 0 or done == tot:
            write_status(job, "processing", progress=(done, tot))

    cap.release(); vw.release()
    if first_snap is not None:
        Image.fromarray(first_snap).save(job / "out.jpg")

    note = f"{total_ms:.2f} ms ({done}f, avg {total_ms/max(done,1):.2f} ms/f)"
    (job / "hw_time.txt").write_text(note)
    write_status(job, "merging")                  # quick stage
    write_status(job, "finished", note=note, progress=(done, done))
    (job / "done.txt").write_text("done")
    log.info("✔ VIDEO job %s finished (%s)", job.name, note)

# --------------------------------------------------------------------------- #
# Startup recovery
# --------------------------------------------------------------------------- #
def reset_incomplete_jobs() -> None:
    """
    If the worker crashed mid‑job, stage == 'processing'/'merging'.
    Roll such jobs back to 'queued' so they re-run from scratch.
    """
    for job in JOBS_DIR.iterdir():
        if (job / "done.txt").exists() or (job / "error.txt").exists():
            continue
        st = _read_status(job).get("stage", "queued")
        if st in ("processing", "merging", "kernel_loaded"):
            log.warning("restoring job %s from interrupted state «%s»", job.name, st)
            write_status(job, "queued")

# --------------------------------------------------------------------------- #
# Main loop
# --------------------------------------------------------------------------- #
def main() -> None:
    log.info("Worker started, watching %s", JOBS_DIR)
    reset_incomplete_jobs()

    while True:
        # FIFO: earliest mtime first
        pending = sorted(
            (j for j in JOBS_DIR.iterdir()
             if not (j / "done.txt").exists() and not (j / "error.txt").exists()),
            key=lambda p: p.stat().st_mtime
        )
        if not pending:
            time.sleep(0.5)
            continue

        job = pending[0]
        try:
            kind = (job / "kernel.txt").read_text().strip()
        except FileNotFoundError:
            log.error("job %s has no kernel.txt → marking error", job.name)
            (job / "error.txt").write_text("missing kernel")
            write_status(job, "error", note="missing kernel.txt")
            continue

        try:
            cur_stage = _read_status(job).get("stage", "queued")
            if cur_stage == "queued":
                write_status(job, "receiving")

            if kind in ("grayscale", "filter"):
                process_image(job, kind)
            elif kind in ("grayscale_video", "filter_video"):
                process_video(job, kind)
            else:
                raise ValueError(f"unknown kernel «{kind}»")

        except Exception as exc:
            log.error("Exception while processing %s: %s", job.name, exc)
            log.debug("Trace:\n%s", traceback.format_exc())
            (job / "error.txt").write_text(str(exc))
            write_status(job, "error", note=str(exc))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("Worker interrupted - shutting down")
