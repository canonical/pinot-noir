"""
Production settings for pinot_noir project.

Reads all sensitive configuration from environment variables.
Required environment variables:
  SECRET_KEY     - Django secret key
  DB_NAME        - PostgreSQL database name
  DB_USER        - PostgreSQL user
  DB_PASSWORD    - PostgreSQL password
  ALLOWED_HOSTS  - Comma-separated list of allowed hostnames

Optional environment variables:
  DB_HOST        - PostgreSQL host (default: localhost)
  DB_PORT        - PostgreSQL port (default: 5432)
"""

import os

from .base import *

SECRET_KEY = os.environ["SECRET_KEY"]

DEBUG = False

ALLOWED_HOSTS = os.environ["ALLOWED_HOSTS"].split(",")


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ["DB_NAME"],
        "USER": os.environ["DB_USER"],
        "PASSWORD": os.environ["DB_PASSWORD"],
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
    }
}
