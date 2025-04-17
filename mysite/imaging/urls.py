# mysite/imaging/urls.py
from django.urls import path
from .views import HomeView, GrayscalePageView, FilterPageView, HistoryPageView

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("grayscale/", GrayscalePageView.as_view(), name="grayscale_page"),
    path("filter/",    FilterPageView.as_view(),    name="filter_page"),
    path("history/",   HistoryPageView.as_view(),   name="history_page"),
]
