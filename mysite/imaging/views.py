# mysite/imaging/views.py
from django.views.generic import TemplateView

class HomeView(TemplateView):
    template_name = "imaging/home.html"

class GrayscalePageView(TemplateView):
    template_name = "imaging/grayscale.html"

class FilterPageView(TemplateView):
    template_name = "imaging/filter.html"

class HistoryPageView(TemplateView):
    template_name = "imaging/history.html"

class VideoGrayscalePageView(TemplateView):
    template_name = "imaging/video_grayscale.html"

class VideoFilterPageView(TemplateView):
    template_name = "imaging/video_filter.html"
