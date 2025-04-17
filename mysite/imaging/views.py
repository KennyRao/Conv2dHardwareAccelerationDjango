# mysite/imaging/views.py
from django.views.generic import TemplateView
from django.shortcuts import render
from .forms import GrayscaleForm, FilterForm

class HomeView(TemplateView):
    template_name = "home.html"

class GrayscalePageView(TemplateView):
    template_name = "grayscale.html"

class FilterPageView(TemplateView):
    template_name = "filter.html"
