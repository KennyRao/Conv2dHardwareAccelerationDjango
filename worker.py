# worker.py
import os
import time
from PIL import Image
import numpy as np
from pynq import Overlay, allocate, DefaultIP

jobs_dir = '/home/xilinx/f_c_a_api/mysite/api/jobs'
current_overlay = None
current_ip = None
current_dma = None
loaded_kernel = None

overlay_paths = {
    'grayscale': '/home/xilinx/pynq/overlays/grayscale/grayscale.bit',
    'filter': '/home/xilinx/pynq/overlays/filter/filter.bit',
}

class FilterKernel(DefaultIP):
    bindto = ['xilinx.com:hls:filter_kernel:1.0']
    def __init__(self, description):
        super().__init__(description=description)
        self.width_addr = self.register_map.image_width.address
        self.height_addr = self.register_map.image_height.address
        self.factor_addr = self.register_map.kernel_factor.address
        self.kernel_addr = 0x40
    
    @property
    def width(self):
        return self.read(self.width_addr)
    
    @width.setter
    def width(self, value):
        self.write(self.width_addr, value)
    
    @property
    def height(self):
        return self.read(self.height_addr)
    
    @height.setter
    def height(self, value):
        self.write(self.height_addr, value)
        
    @property
    def factor(self):
        return self.read(self.factor_addr)
    
    @factor.setter
    def factor(self, value):
        self.write(self.factor_addr, value)
    
    @property
    def kernel(self):
        coefficients = []
        for i in range(9):
            value = self.read(self.kernel_addr + (4 * i))
            coefficients.append(value)
        return np.array(coefficients, dtype=np.int32).reshape(3, 3)
    
    @kernel.setter
    def kernel(self, matrix):
        matrix = np.array(matrix, dtype=np.int32)
        if matrix.shape != (3, 3):
            raise ValueError(f"Kernel must be 3x3, got {matrix.shape}")
        flat_coeffs = matrix.flatten()
        for i, value in enumerate(flat_coeffs):
            self.write(self.kernel_addr + (4 * i), int(value))

def load_overlay(kernel):
    global current_overlay, current_ip, current_dma, loaded_kernel
    if loaded_kernel == kernel:
        return  # already loaded
    
    path = overlay_paths.get(kernel)
    if not path:
        raise ValueError(f"Unsupported kernel: {kernel}")
    
    current_overlay = Overlay(path)
    match kernel:
        case 'grayscale':
            current_ip = current_overlay.grayscale_kernel_0
        case 'filter':
            current_ip = current_overlay.filter_kernel_0
            
    current_dma = current_overlay.axi_dma_0
    loaded_kernel = kernel

def grayscale(img_array):
        global current_ip
        h, w, _ = img_array.shape
        current_ip.write(0x10, w)
        current_ip.write(0x18, h)

def filter(combined, job_path):
    with open(os.path.join(job_path, 'factor.txt')) as f:
        factor = int(f.read().strip())
    with open(os.path.join(job_path, 'filter.txt')) as f:
        filter_str = f.read().strip()
        filter_values = list(map(int, filter_str.split()))
        if len(filter_values) != 9:
            raise ValueError("filter.txt must contain exactly 9 values")
        filter_matrix = np.array(filter_values, dtype=np.int32).reshape(3, 3)
    
    current_ip.height = combined.shape[0]
    current_ip.width = combined.shape[1]
    current_ip.factor = factor
    current_ip.kernel = filter_matrix

while True:
    for job_name in os.listdir(jobs_dir):
        job_path = os.path.join(jobs_dir, job_name)
        done_flag = os.path.join(job_path, 'done.txt')

        if os.path.exists(done_flag):   # if job is already completed skip
            continue

        try:
            print(f"Processing job: {job_name}")
            with open(os.path.join(job_path, 'kernel.txt')) as f:
                kernel = f.read().strip()
            
            load_overlay(kernel)

            img = Image.open(os.path.join(job_path, 'in.jpg'))
            img_array = np.array(img)
            combined = ((img_array[:,:,0].astype(np.uint32) << 16) |
                        (img_array[:,:,1].astype(np.uint32) << 8) |
                         img_array[:,:,2].astype(np.uint32))

            in_buffer = allocate(combined.shape, dtype=np.uint32)
            in_buffer[:] = combined
            out_buffer = allocate(combined.shape, dtype=np.uint32)

            match kernel:
                case 'grayscale':
                    grayscale(img_array)
                case 'filter':
                    filter(combined, job_path)

            current_ip.write(0x00, 1)
            current_dma.sendchannel.transfer(in_buffer)
            current_dma.recvchannel.transfer(out_buffer)
            current_dma.sendchannel.wait()
            current_dma.recvchannel.wait()

            r = (out_buffer >> 16) & 0xFF
            g = (out_buffer >> 8) & 0xFF
            b = out_buffer & 0xFF
            result_img = np.stack((r, g, b), axis=-1).astype(np.uint8)

            Image.fromarray(result_img).save(os.path.join(job_path, 'out.jpg'))
            in_buffer.freebuffer()
            out_buffer.freebuffer()

            # signal done
            with open(done_flag, 'w') as f:
                f.write('done')
            print(f"Completed {job_name}")

        except Exception as e:
            print("Worker error:", e)

