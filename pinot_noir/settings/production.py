"""
Production settings for pinot_noir project.

Reads all sensitive configuration from environment variables.
Required environment variables:
  DJANGO_SECRET_KEY - Django secret key
  DJANGO_FIELD_ENCRYPTION_KEY_VALUE - Key used to encrypt sensitive model fields
  DJANGO_ALLOWED_HOSTS - JSON-encoded list of allowed hostnames
  DJANGO_BASE_URL - Public base URL, used as the trusted CSRF origin
  GOOGLE_OAUTH_CLIENT_ID - Optional Google OAuth web client ID
  GOOGLE_OAUTH_CLIENT_SECRET - Optional Google OAuth web client secret
  POSTGRESQL_DB_NAME - PostgreSQL database name
  POSTGRESQL_DB_USERNAME - PostgreSQL user
  POSTGRESQL_DB_PASSWORD - PostgreSQL password
  POSTGRESQL_DB_HOSTNAME - PostgreSQL host
  POSTGRESQL_DB_PORT - PostgreSQL port
"""

import json
import os

from .base import *

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]

# Dedicated key for encrypting sensitive model fields, independent of
# SECRET_KEY so the latter can be rotated without losing stored secrets.
FIELD_ENCRYPTION_KEY = os.environ["DJANGO_FIELD_ENCRYPTION_KEY_VALUE"]

DEBUG = False

ALLOWED_HOSTS = json.loads(os.environ["DJANGO_ALLOWED_HOSTS"])

CSRF_TRUSTED_ORIGINS = [os.environ["DJANGO_BASE_URL"]]


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ["POSTGRESQL_DB_NAME"],
        "USER": os.environ["POSTGRESQL_DB_USERNAME"],
        "PASSWORD": os.environ["POSTGRESQL_DB_PASSWORD"],
        "HOST": os.environ["POSTGRESQL_DB_HOSTNAME"],
        "PORT": os.environ["POSTGRESQL_DB_PORT"],
    }
}
