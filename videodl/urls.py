from django.urls import path

from downloader import views

urlpatterns = [
    path("", views.index, name="index"),
    path("formats", views.formats, name="formats"),
    path("download", views.download, name="download"),
    path("healthz", views.healthz, name="healthz"),
]
