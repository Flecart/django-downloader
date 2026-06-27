from django.templatetags.static import static
from django.urls import path
from django.views.generic.base import RedirectView

from downloader import views

urlpatterns = [
    path("", views.index, name="index"),
    path("formats", views.formats, name="formats"),
    path("download", views.download, name="download"),
    path("healthz", views.healthz, name="healthz"),
    # Browsers auto-request /favicon.ico at the site root; point it at the static file.
    path(
        "favicon.ico",
        RedirectView.as_view(url=static("downloader/favicon.ico"), permanent=True),
    ),
]
