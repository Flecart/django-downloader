"""
Django settings for the videodl project.

Kept intentionally lean so it runs both locally and on Vercel's serverless
Python runtime. No database-backed apps are enabled, so there is nothing to
migrate and nothing that depends on persistent disk (which Vercel does not
provide).
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY: set DJANGO_SECRET_KEY in the environment for production / Vercel.
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "dev-insecure-key-change-me-in-production",
)

DEBUG = os.environ.get("DJANGO_DEBUG", "False").lower() == "true"

# Vercel serves the app from *.vercel.app; allow it plus any custom domain.
ALLOWED_HOSTS = ["*"]

CSRF_TRUSTED_ORIGINS = [
    "https://*.vercel.app",
]

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "downloader",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "videodl.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "downloader.context_processors.app_version",
            ],
        },
    },
]

WSGI_APPLICATION = "videodl.wsgi.application"

# No database is used by this app.
DATABASES = {}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles_build"
# Serve static files via Django's finders at runtime so no `collectstatic`
# build step is required. Vercel has no Django build phase, and WhiteNoise in
# finders mode reads straight from each app's static/ directory (which is
# bundled with the function). For a high-traffic host, run collectstatic and
# drop these two lines to use the compressed/manifest storage instead.
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# How long (seconds) to allow yt-dlp metadata extraction before giving up.
# Keep below the serverless function timeout configured in vercel.json.
YTDLP_TIMEOUT = int(os.environ.get("YTDLP_TIMEOUT", "30"))
