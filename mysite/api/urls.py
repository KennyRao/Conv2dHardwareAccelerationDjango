# mysite/api/urls.py
from django.urls import path
from .views import (
    GrayscaleAPIView, FilterAPIView,
    VideoGrayscaleAPIView, VideoFilterAPIView, VideoResultAPIView,
    HistoryAPIView, TestAPIView
)

urlpatterns = [
    # Image endpoints
    path("grayscale/", GrayscaleAPIView.as_view(), name="api_grayscale"),
    path("filter/",    FilterAPIView.as_view(),    name="api_filter"),

    # Video endpoints
    path("video/grayscale/",           VideoGrayscaleAPIView.as_view(), name="api_video_grayscale"),
    path("video/filter/",              VideoFilterAPIView.as_view(),    name="api_video_filter"),
    path("video/result/<str:job_id>/", VideoResultAPIView.as_view(),    name="api_video_result"),

    # Misc
    path("history/", HistoryAPIView.as_view(), name="api_history"),
    path("test/",    TestAPIView.as_view()),
]
