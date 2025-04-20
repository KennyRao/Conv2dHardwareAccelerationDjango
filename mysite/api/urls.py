# mysite/api/urls.py
from django.urls import path
from .views import (
    GrayscaleAPIView, FilterAPIView,
    VideoGrayscaleAPIView, VideoFilterAPIView,
    VideoResultAPIView, ImageResultAPIView,
    HistoryAPIView, TestAPIView
)

urlpatterns = [
    # Image endpoints
    path("grayscale/", GrayscaleAPIView.as_view(), name="api_grayscale"),
    path("filter/",    FilterAPIView.as_view(),    name="api_filter"),

    # Video endpoints
    path("video/grayscale/",           VideoGrayscaleAPIView.as_view(), name="api_video_grayscale"),
    path("video/filter/",              VideoFilterAPIView.as_view(),    name="api_video_filter"),
    
    # Result endpoints
    path("video/result/<str:job_id>/", VideoResultAPIView.as_view(),    name="api_video_result"),
    path("image/result/<str:job_id>/", ImageResultAPIView.as_view(),    name="api_image_result"),

    # Misc
    path("history/", HistoryAPIView.as_view(), name="api_history"),
    path("test/",    TestAPIView.as_view()),
]
