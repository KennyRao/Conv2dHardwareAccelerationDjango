# mysite/imaging/urls.py
from django.urls import path
from .views import (
    HomeView, GrayscalePageView, FilterPageView, HistoryPageView,
    VideoGrayscalePageView, VideoFilterPageView
)

urlpatterns = [
    path("", HomeView.as_view(), name="home"),

    # images
    path("grayscale/", GrayscalePageView.as_view(), name="grayscale_page"),
    path("filter/", FilterPageView.as_view(), name="filter_page"),

    # videos
    path("video/grayscale/", VideoGrayscalePageView.as_view(), name="video_grayscale_page"),
    path("video/filter/",    VideoFilterPageView.as_view(), name="video_filter_page"),

    # misc
    path("history/", HistoryPageView.as_view(), name="history_page"),
]
