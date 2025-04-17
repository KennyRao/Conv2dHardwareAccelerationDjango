# worker.py
"""
Background FPGA worker – images & videos.
"""

import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from pynq import Overlay, allocate, DefaultIP

JOBS_DIR = Path("/home/xilinx/f_c_a_api/mysite/api/jobs")
MAX_W, MAX_H = 1920, 1080
current_overlay = current_ip = current_dma = loaded_kernel = None

OVERLAY_PATHS = {
    "grayscale": "/home/xilinx/pynq/overlays/grayscale/grayscale.bit",
    "filter":    "/home/xilinx/pynq/overlays/filter/filter.bit",
}


# --------------------------------------------------------------------------- #
# Custom driver for the HLS 3×3 filter kernel
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
        data = [self.read(self.kernel_addr + 4 * i) for i in range(9)]
        return np.array(data, dtype=np.int32).reshape(3, 3)

    @kernel.setter
    def kernel(self, matrix):
        flat = np.array(matrix, dtype=np.int32).flatten()
        if flat.size != 9:
            raise ValueError("Kernel must be 3×3")
        for i, val in enumerate(flat):
            self.write(self.kernel_addr + 4 * i, int(val))


# --------------------------------------------------------------------------- #
# Overlay management
# --------------------------------------------------------------------------- #
def load_overlay(kind: str):
    """Load bitstream only when it differs from the one already loaded."""
    global current_overlay, current_ip, current_dma, loaded_kernel
    if loaded_kernel == kind:
        return
    current_overlay = Overlay(OVERLAY_PATHS[kind.removesuffix("_video")])
    current_dma     = current_overlay.axi_dma_0
    current_ip      = (current_overlay.grayscale_kernel_0
                       if kind.startswith("grayscale")
                       else current_overlay.filter_kernel_0)
    loaded_kernel   = kind


# ────────────────────────────────────────────────────────────────────────────
# Per‑frame FPGA helper
# ────────────────────────────────────────────────────────────────────────────
def process_frame(rgb: np.ndarray, cfg_fun):
    comb = ((rgb[..., 0].astype(np.uint32) << 16) |
            (rgb[..., 1].astype(np.uint32) << 8)  |
             rgb[..., 2].astype(np.uint32))
    in_b  = allocate(comb.shape, dtype=np.uint32)
    out_b = allocate(comb.shape, dtype=np.uint32)
    in_b[:] = comb

    cfg_fun(rgb)
    current_ip.write(0x00, 1)
    current_dma.sendchannel.transfer(in_b)
    current_dma.recvchannel.transfer(out_b)
    current_dma.sendchannel.wait()
    current_dma.recvchannel.wait()

    r = (out_b >> 16) & 0xFF
    g = (out_b >>  8) & 0xFF
    b =  out_b        & 0xFF
    out = np.stack((r, g, b), -1).astype(np.uint8)

    in_b.freebuffer()
    out_b.freebuffer()
    return out


# ────────────────────────────────────────────────────────────────────────────
# Config helpers
# ────────────────────────────────────────────────────────────────────────────
def cfg_grayscale(arr):  # arr: RGB
    h, w = arr.shape[:2]
    current_ip.write(0x10, w)
    current_ip.write(0x18, h)


def cfg_filter(arr, job):
    h, w = arr.shape[:2]
    current_ip.height = h
    current_ip.width  = w
    current_ip.factor = int((job / "factor.txt").read_text())
    k = np.fromstring((job / "filter.txt").read_text(), sep=' ',
                      dtype=np.int32).reshape(3, 3)
    current_ip.kernel = k


# ────────────────────────────────────────────────────────────────────────────
# Image job
# ────────────────────────────────────────────────────────────────────────────
def handle_image(job, kind):
    load_overlay(kind)
    img = np.array(Image.open(job / "in.jpg"))
    cfg = cfg_grayscale if kind == "grayscale" else lambda a: cfg_filter(a, job)

    t0 = time.perf_counter()
    res = process_frame(img, cfg)
    t1 = time.perf_counter()
    (job / "hw_time.txt").write_text(f"{(t1-t0)*1e3:.2f} ms")
    Image.fromarray(res).save(job / "out.jpg")
    (job / "done.txt").write_text("done")
    print("✓", job.name)


# ────────────────────────────────────────────────────────────────────────────
# Video job
# ────────────────────────────────────────────────────────────────────────────
def handle_video(job, kind):
    load_overlay(kind)
    cap = cv2.VideoCapture(str(job / "in.mp4"))
    if not cap.isOpened():
        raise RuntimeError("Video open failed")

    fps  = cap.get(cv2.CAP_PROP_FPS) or 25.0
    w    = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h    = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    scl  = max(w/MAX_W, h/MAX_H, 1.0)
    ow, oh = int(w/scl), int(h/scl)

    vw = cv2.VideoWriter(str(job / "out.mp4"),
                         cv2.VideoWriter_fourcc(*"mp4v"), fps, (ow, oh))
    cfg = cfg_grayscale if kind == "grayscale_video" else lambda a: cfg_filter(a, job)

    first_snap = None
    frames = 0
    t0 = time.perf_counter()
    while True:
        ok, frm = cap.read()
        if not ok:
            break
        if scl > 1.0:
            frm = cv2.resize(frm, (ow, oh), cv2.INTER_AREA)
        rgb = cv2.cvtColor(frm, cv2.COLOR_BGR2RGB)
        out = process_frame(rgb, cfg)
        if first_snap is None:
            first_snap = out.copy()
        vw.write(cv2.cvtColor(out, cv2.COLOR_RGB2BGR))
        frames += 1

    t1 = time.perf_counter()
    cap.release()
    vw.release()
    if first_snap is not None:
        Image.fromarray(first_snap).save(job / "out.jpg")  # snapshot
    (job / "hw_time.txt").write_text(f"{(t1-t0)*1e3:.2f} ms ({frames}f)")
    (job / "done.txt").write_text("done")
    print("✓", job.name, f"({frames} frames)")


# --------------------------------------------------------------------------- #
# Main loop
# --------------------------------------------------------------------------- #
while True:
    for p in Path(JOBS_DIR).iterdir():
        if (p / "done.txt").exists():
            continue
        try:
            k = (p / "kernel.txt").read_text().strip()
            if k in ("grayscale", "filter"):
                handle_image(p, k)
            elif k in ("grayscale_video", "filter_video"):
                handle_video(p, k)
            else:
                print("Unknown kernel:", k)
        except Exception as e:
            print("Worker error:", e)
    time.sleep(0.5)
