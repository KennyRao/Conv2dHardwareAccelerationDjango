# worker.py
"""
Background FPGA worker – images & videos.
"""

from __future__ import annotations
import os, sys, time, traceback
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from pynq import Overlay, allocate, DefaultIP

# ────────────────────────────────────────────────────────────────────────────
# Logging configuration
# ────────────────────────────────────────────────────────────────────────────
import logging

_DEBUG = bool(int(os.getenv("WORKER_DEBUG", "0")))
logging.basicConfig(
    level=logging.DEBUG if _DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("worker")

# ────────────────────────────────────────────────────────────────────────────
# Constants
# ────────────────────────────────────────────────────────────────────────────
JOBS_DIR = Path("/home/xilinx/f_c_a_api/mysite/api/jobs")
MAX_W, MAX_H = 1920, 1080  # resize cap for large videos

OVERLAY_PATHS = {
    "grayscale": "/home/xilinx/pynq/overlays/grayscale/grayscale.bit",
    "filter":    "/home/xilinx/pynq/overlays/filter/filter.bit",
}

current_overlay = current_ip = current_dma = loaded_kernel = None

# ────────────────────────────────────────────────────────────────────────────
# HLS 3×3 filter – custom driver
# ────────────────────────────────────────────────────────────────────────────
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
        return np.array([self.read(self.kernel_addr + 4*i) for i in range(9)],
                        np.int32).reshape(3, 3)

    @kernel.setter
    def kernel(self, m):
        flat = np.array(m, np.int32).ravel()
        if flat.size != 9:
            raise ValueError("Kernel must be 3×3")
        for i, v in enumerate(flat):
            self.write(self.kernel_addr + 4*i, int(v))

# ────────────────────────────────────────────────────────────────────────────
# Overlay management
# ────────────────────────────────────────────────────────────────────────────
def load_overlay(kind: str):
    """
    Load the required bitstream only if it differs from the current one.
    `kind` may be "grayscale", "filter", "grayscale_video", "filter_video".
    """
    global current_overlay, current_ip, current_dma, loaded_kernel

    base = kind.removesuffix("_video")
    if loaded_kernel == base:
        log.debug("Overlay '%s' already loaded – skip", base)
        return

    bit_path = OVERLAY_PATHS[base]
    log.info("Loading overlay %s → %s", base, bit_path)
    t0 = time.perf_counter()
    current_overlay = Overlay(bit_path)
    elapsed = (time.perf_counter() - t0) * 1e3
    log.info("Overlay loaded in %.1f ms", elapsed)

    current_dma = current_overlay.axi_dma_0
    current_ip  = (current_overlay.grayscale_kernel_0
                   if base == "grayscale" else current_overlay.filter_kernel_0)
    loaded_kernel = base

# ────────────────────────────────────────────────────────────────────────────
# FPGA transfer helper
# ────────────────────────────────────────────────────────────────────────────
def process_frame(rgb: np.ndarray, cfg_fun) -> tuple[np.ndarray, float]:
    """
    Send `rgb` frame (H×W×3 uint8) through the accelerator.
    Returns (processed_frame, elapsed_ms).
    """
    comb = ((rgb[..., 0].astype(np.uint32) << 16) |
            (rgb[..., 1].astype(np.uint32) <<  8) |
             rgb[..., 2].astype(np.uint32))

    in_buf  = allocate(comb.shape, dtype=np.uint32)
    out_buf = allocate(comb.shape, dtype=np.uint32)
    in_buf[:] = comb

    cfg_fun(rgb)                       # program registers
    current_ip.write(0x00, 1)          # start

    t0 = time.perf_counter()
    current_dma.sendchannel.transfer(in_buf)
    current_dma.recvchannel.transfer(out_buf)
    current_dma.sendchannel.wait()
    current_dma.recvchannel.wait()
    elapsed = (time.perf_counter() - t0) * 1e3

    r = (out_buf >> 16) & 0xFF
    g = (out_buf >>  8) & 0xFF
    b =  out_buf        & 0xFF
    out = np.stack((r, g, b), -1).astype(np.uint8)

    in_buf.freebuffer(); out_buf.freebuffer()
    log.debug("DMA transfer complete – %.2f ms", elapsed)
    return out, elapsed

# ────────────────────────────────────────────────────────────────────────────
# Config helpers
# ────────────────────────────────────────────────────────────────────────────
def cfg_grayscale(arr):               # arr = RGB frame
    h, w = arr.shape[:2]
    current_ip.write(0x10, w)
    current_ip.write(0x18, h)

def cfg_filter(arr, job):
    h, w = arr.shape[:2]
    current_ip.height = h
    current_ip.width  = w
    current_ip.factor = int((job / "factor.txt").read_text())
    k = np.fromstring((job / "filter.txt").read_text(), sep=" ",
                      dtype=np.int32).reshape(3, 3)
    current_ip.kernel = k

# ────────────────────────────────────────────────────────────────────────────
# Job handlers
# ────────────────────────────────────────────────────────────────────────────
def handle_image(job: Path, kind: str):
    log.info("▶ IMAGE job %s (%s)", job.name, kind)
    load_overlay(kind)
    img = np.array(Image.open(job / "in.jpg"))
    cfg = cfg_grayscale if kind == "grayscale" else lambda a: cfg_filter(a, job)

    out, t_ms = process_frame(img, cfg)
    Image.fromarray(out).save(job / "out.jpg")
    (job / "hw_time.txt").write_text(f"{t_ms:.2f} ms")
    (job / "done.txt").write_text("done")
    log.info("✔ IMAGE job %s complete (%.2f ms)", job.name, t_ms)

def handle_video(job: Path, kind: str):
    log.info("▶ VIDEO job %s (%s)", job.name, kind)
    load_overlay(kind)

    cap = cv2.VideoCapture(str(job / "in.mp4"))
    if not cap.isOpened():
        raise RuntimeError("Failed to open input video")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    w   = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h   = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    scale = max(w/MAX_W, h/MAX_H, 1.0)
    ow, oh = int(w/scale), int(h/scale)

    vw = cv2.VideoWriter(str(job / "out.mp4"),
                         cv2.VideoWriter_fourcc(*"mp4v"), fps, (ow, oh))
    cfg = cfg_grayscale if kind == "grayscale_video" else lambda a: cfg_filter(a, job)

    first_snap = None
    frames, total_ms = 0, 0.0
    while True:
        ok, frm = cap.read()
        if not ok:
            break
        if scale > 1.0:
            frm = cv2.resize(frm, (ow, oh), cv2.INTER_AREA)
        rgb = cv2.cvtColor(frm, cv2.COLOR_BGR2RGB)
        out, t_ms = process_frame(rgb, cfg)
        total_ms += t_ms
        if first_snap is None:
            first_snap = out.copy()
        vw.write(cv2.cvtColor(out, cv2.COLOR_RGB2BGR))
        frames += 1
        log.debug("Frame %5d processed (%.2f ms)", frames, t_ms)

    cap.release(); vw.release()
    if first_snap is not None:
        Image.fromarray(first_snap).save(job / "out.jpg")

    (job / "hw_time.txt").write_text(
        f"{total_ms:.2f} ms ({frames}f, avg {total_ms/frames if frames else 0:.2f} ms)"
    )
    (job / "done.txt").write_text("done")
    log.info("✔ VIDEO job %s complete – %d frames, total %.2f ms",
             job.name, frames, total_ms)

# ────────────────────────────────────────────────────────────────────────────
# Main loop
# ────────────────────────────────────────────────────────────────────────────
def main():
    log.info("Worker started. Watching %s", JOBS_DIR)
    while True:
        for job in JOBS_DIR.iterdir():
            if (job / "done.txt").exists():
                continue
            try:
                kind = (job / "kernel.txt").read_text().strip()
                if kind in ("grayscale", "filter"):
                    handle_image(job, kind)
                elif kind in ("grayscale_video", "filter_video"):
                    handle_video(job, kind)
                else:
                    log.warning("Unknown kernel '%s' in %s", kind, job.name)
                    (job / "done.txt").write_text("error")
            except Exception as exc:
                log.error("Exception while processing %s: %s", job.name, exc)
                log.debug("Traceback:\n%s", traceback.format_exc())
                (job / "done.txt").write_text("error")
        time.sleep(0.5)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("Worker interrupted – shutting down")
