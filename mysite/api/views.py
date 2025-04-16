# mysite/api/views.py
from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from PIL import Image
from django.shortcuts import render
import os
import io
from django.http import FileResponse
import uuid
import time
from django.http import HttpResponse
import shutil

# Create your views here.
class TestAPIView(APIView):
    def get(self, request):
        return Response({"message": "Working fine!"})

def grayscale_test_view(request):
    return render(request, 'grayscale_post_test.html')

def filter_test_view(request):
    return render(request, 'filter_post_test.html')
    
class GrayscaleAPIView(APIView):
    parser_classes = (MultiPartParser, FormParser)

    def get(self, request):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        image_path = os.path.join(current_dir, 'test_img', 'input.jpg')
        image = Image.open(image_path).convert('L') 
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG")
        buffer.seek(0)
        return FileResponse(buffer, content_type='image/jpeg')

    def post(self, request):
        uploaded_file = request.FILES.get('image')
        if not uploaded_file:
            return Response({"error": "No image uploaded"}, status=400)

        job_id = f"job_{uuid.uuid4().hex}"
        base_dir = os.path.dirname(os.path.abspath(__file__))
        jobs_dir = os.path.join(base_dir, 'jobs')
        job_path = os.path.join(jobs_dir, job_id)
        os.makedirs(job_path, exist_ok=True)
        input_path = os.path.join(job_path, 'in.jpg')

        # Open image using PIL and save to job folder
        image = Image.open(uploaded_file).save(input_path)

        with open(os.path.join(job_path, 'kernel.txt'), 'w') as f:
            f.write('grayscale')


        done_path = os.path.join(job_path, 'done.txt')
        output_path = os.path.join(job_path, 'out.jpg')

        for _ in range(30):  # wait up to 30 seconds
            if os.path.exists(done_path) and os.path.exists(output_path):
                with open(output_path, 'rb') as f:
                    image_bytes = f.read()

                # Cleanup job folder after response is prepared
                try:
                    shutil.rmtree(job_path)
                except Exception as cleanup_err:
                    print(f"Cleanup error (grayscale): {cleanup_err}")
                return HttpResponse(image_bytes, content_type='image/jpeg')
            time.sleep(1)

        return JsonResponse({"error": "Timeout or processing failed"}, status=504)

class FilterAPIView(APIView):
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request):
        uploaded_file = request.FILES.get('image')
        if not uploaded_file:
            return Response({"error": "No image uploaded"}, status=400)
        
        filter_str = request.POST.get('filter')
        factor_str = request.POST.get('factor')
        if not filter_str or not factor_str:
            return Response({"error": "Missing 'filter' or 'factor'"}, status=400)

        try:
            filter_values = list(map(int, filter_str.strip().split()))
            if len(filter_values) != 9:
                raise ValueError
            factor = int(factor_str.strip())
        except ValueError:
            return Response({"error": "Invalid filter or factor format"}, status=400)

        job_id = f"job_{uuid.uuid4().hex}"
        base_dir = os.path.dirname(os.path.abspath(__file__))
        jobs_dir = os.path.join(base_dir, 'jobs')
        job_path = os.path.join(jobs_dir, job_id)
        os.makedirs(job_path, exist_ok=True)
        input_path = os.path.join(job_path, 'in.jpg')

        # Open image using PIL and save to job folder
        image = Image.open(uploaded_file).save(input_path)

        with open(os.path.join(job_path, 'kernel.txt'), 'w') as f:
            f.write('filter')

        with open(os.path.join(job_path, 'filter.txt'), 'w') as f:
            f.write(filter_str.strip())

        with open(os.path.join(job_path, 'factor.txt'), 'w') as f:
            f.write(str(factor))

        done_path = os.path.join(job_path, 'done.txt')
        output_path = os.path.join(job_path, 'out.jpg')

        for _ in range(30):  # wait up to 30 seconds
            if os.path.exists(done_path) and os.path.exists(output_path):
                with open(output_path, 'rb') as f:
                    image_bytes = f.read()

                # Cleanup job folder after response is prepared
                try:
                    shutil.rmtree(job_path)
                except Exception as cleanup_err:
                    print(f"Cleanup error (grayscale): {cleanup_err}")
                return HttpResponse(image_bytes, content_type='image/jpeg')
            time.sleep(1)

        return JsonResponse({"error": "Timeout or processing failed"}, status=504)