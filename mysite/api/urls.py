# mysite/api/urls.py
from django.urls import path
from .views import FilterAPIView, GrayscaleAPIView, TestAPIView, HistoryAPIView

urlpatterns = [
    path("grayscale/", GrayscaleAPIView.as_view(), name="api_grayscale"),
    path("filter/",    FilterAPIView.as_view(),    name="api_filter"),
    path("history/",   HistoryAPIView.as_view(),   name="api_history"),
    path("test/",      TestAPIView.as_view()),
]
