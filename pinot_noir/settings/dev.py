"""
Development settings for pinot_noir project.

Uses SQLite and insecure fallback secret keys. DJANGO_* environment variables
override the local defaults. Not suitable for production.
"""

import json
import os

from .base import *

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY", "django-insecure-t+yf%^(vi5zm+fd!#o=a%bh7c6=8fub+z@!ji*2=hdzno^=7op"
)

# SECURITY WARNING: keep the field encryption key used in production secret!
# Used to encrypt sensitive model fields (e.g. stored API tokens). Kept
# separate from SECRET_KEY so the latter can be rotated independently.
FIELD_ENCRYPTION_KEY = os.environ.get(
    "DJANGO_FIELD_ENCRYPTION_KEY_VALUE", "django-insecure-encryption-key-pmh2!8w=q3xv0&zr+f^t1ng"
)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

STORAGES = {
    **STORAGES,
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

ALLOWED_HOSTS = json.loads(os.environ.get("DJANGO_ALLOWED_HOSTS", '["*"]'))

CSRF_TRUSTED_ORIGINS = [os.environ["DJANGO_BASE_URL"]] if os.environ.get("DJANGO_BASE_URL") else []


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",  # noqa: F405
    }
}
