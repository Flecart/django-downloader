"""Vercel serverless entry point.

The @vercel/python runtime imports this module and serves the module-level
WSGI callable named `app`.
"""
import os
import sys
from pathlib import Path

# Make the project root importable when running inside Vercel's bundler.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "videodl.settings")

from videodl.wsgi import application  # noqa: E402

app = application
