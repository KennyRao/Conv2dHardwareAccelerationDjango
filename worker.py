# worker.py
"""
Background FPGA worker – continuously polls *jobs* directory, applies the
requested accelerator (grayscale / 3×3 filter), writes JPEG result plus a
'done.txt' *and* a 'hw_time.txt' containing runtime in milliseconds.
"""
import os
import time
from pathlib import Path

import numpy as np
from PIL import Image
from pynq import Overlay, allocate, DefaultIP

JOBS_DIR = Path("/home/xilinx/f_c_a_api/mysite/api/jobs")
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

    def __init__(self, description):
        super().__init__(description=description)
        self.width_addr   = self.register_map.image_width.address
        self.height_addr  = self.register_map.image_height.address
        self.factor_addr  = self.register_map.kernel_factor.address
        self.kernel_addr  = 0x40  # start of 9×int32 kernel matrix

    # Convenience properties
    width  = property(lambda self: self.read(self.width_addr),
                      lambda self, v: self.write(self.width_addr, v))
    height = property(lambda self: self.read(self.height_addr),
                      lambda self, v: self.write(self.height_addr, v))
    factor = property(lambda self: self.read(self.factor_addr),
                      lambda self, v: self.write(self.factor_addr, v))

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

    path = OVERLAY_PATHS[kind]
    current_overlay = Overlay(path)

    match kind:
        case "grayscale":
            current_ip = current_overlay.grayscale_kernel_0
        case "filter":
            current_ip = current_overlay.filter_kernel_0

    current_dma = current_overlay.axi_dma_0
    loaded_kernel = kind


# --------------------------------------------------------------------------- #
# Per‑kernel configuration helpers
# --------------------------------------------------------------------------- #
def cfg_grayscale(img):
    h, w, _ = img.shape
    current_ip.write(0x10, w)
    current_ip.write(0x18, h)


def cfg_filter(img, job_path: Path):
    factor = int((job_path / "factor.txt").read_text())
    values = list(map(int, (job_path / "filter.txt").read_text().split()))
    kernel = np.array(values, dtype=np.int32).reshape(3, 3)

    h, w, _ = img.shape
    current_ip.height = h
    current_ip.width  = w
    current_ip.factor = factor
    current_ip.kernel = kernel


# --------------------------------------------------------------------------- #
# Main loop
# --------------------------------------------------------------------------- #
while True:
    for job_name in os.listdir(JOBS_DIR):
        job_path = JOBS_DIR / job_name
        done_flag = job_path / "done.txt"
        if done_flag.exists():
            continue  # already processed

        try:
            kernel = (job_path / "kernel.txt").read_text().strip()
            load_overlay(kernel)
            img = np.array(Image.open(job_path / "in.jpg"))
            combined = (
                ((img[:, :, 0].astype(np.uint32) << 16) |
                 (img[:, :, 1].astype(np.uint32) << 8) |
                 img[:, :, 2].astype(np.uint32))
            )

            in_buf  = allocate(combined.shape, dtype=np.uint32)
            out_buf = allocate(combined.shape, dtype=np.uint32)
            in_buf[:] = combined

            # Kernel‑specific register setup
            if kernel == "grayscale":
                cfg_grayscale(img)
            else:
                cfg_filter(img, job_path)

            # ----------------------------------------------------------------
            # Measure hardware time
            # ----------------------------------------------------------------
            t0 = time.perf_counter()
            current_ip.write(0x00, 1)          # start
            current_dma.sendchannel.transfer(in_buf)
            current_dma.recvchannel.transfer(out_buf)
            current_dma.sendchannel.wait()
            current_dma.recvchannel.wait()
            hw_ms = (time.perf_counter() - t0) * 1_000
            (job_path / "hw_time.txt").write_text(f"{hw_ms:.2f} ms")

            # ----------------------------------------------------------------
            # Convert 0xRRGGBB back to 3‑channel uint8 image
            # ----------------------------------------------------------------
            r = (out_buf >> 16) & 0xFF
            g = (out_buf >> 8) & 0xFF
            b = out_buf & 0xFF
            result = np.stack((r, g, b), axis=-1).astype(np.uint8)
            Image.fromarray(result).save(job_path / "out.jpg")

            in_buf.freebuffer()
            out_buf.freebuffer()

            done_flag.write_text("done")
            print("✓", job_name)

        except Exception as exc:
            print("Worker error:", exc)

    # Let the worker looks for new jobs roughly twice per second
    time.sleep(0.5)
