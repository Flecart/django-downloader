#!/bin/bash
# Vercel build step: install deps and collect static files into staticfiles_build.
set -e

pip install -r requirements.txt
python manage.py collectstatic --noinput --clear
