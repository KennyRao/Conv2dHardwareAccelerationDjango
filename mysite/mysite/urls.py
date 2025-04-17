# mysite/mysite/urls.py
"""
URL configuration for mysite project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.urls import path, include

# API views
from api.views import (
    TestAPIView,
    GrayscaleAPIView,
    FilterAPIView,
    grayscale_test_view,
    filter_test_view,
)

# Imaging (Bootstrap pages)
from imaging import urls as img_urls

urlpatterns = [
    # Front‑end pages
    path("", include(img_urls)),

    # JSON / binary APIs
    path("api/grayscale/", GrayscaleAPIView.as_view(), name="api_grayscale"),
    path("api/filter/",    FilterAPIView.as_view(),    name="api_filter"),
    path("test/",          TestAPIView.as_view()),

    # Stand‑alone debug pages
    path("grayscale_test/", grayscale_test_view),
    path("filter_test/",    filter_test_view),
]
