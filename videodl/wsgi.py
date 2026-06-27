"""WSGI config for the videodl project."""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "videodl.settings")

application = get_wsgi_application()

# Vercel's @vercel/python runtime looks for a module-level callable named `app`.
app = application
