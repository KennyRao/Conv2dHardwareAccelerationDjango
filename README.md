## worker.py
Manage the PYNQ overlay. \
Run with root
```
/usr/local/share/pynq-venv/bin/python3 worker.py
```
## Django
Frontend and REST API\
Run development mode (No need to root)
```
cd mysite
python3 manage.py runserver 0.0.0.0:8000
```

- PYNQ overlays are generated by Vitis HLS and Vivado synthesis in this [repo](https://github.com/Zichu26/fpga_convolution_acceleration)
