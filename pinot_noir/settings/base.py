"""
Base Django settings for pinot_noir project.

Common settings shared across all environments.
"""

import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent
SITE_ID = 1


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "mozilla_django_oidc",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.sites",
    "django.contrib.messages",
    "django_tasks",
    "django_tasks_db",
    # Pinot Noir base applications
    "pinot_noir.launchpad",
    "pinot_noir.data_manager",
    "pinot_noir.pages",
    # Pinot Noir web page applications
    "pinot_noir.merges_schedule",
    "pinot_noir.reviews",
    "pinot_noir.bug_triage",
    "pinot_noir.site_admin",
    "pinot_noir.user_settings",
    # Custom collectstatic including Vanilla CSS download
    "django.contrib.staticfiles",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "pinot_noir.urls"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "root-redirect"
LOGOUT_REDIRECT_URL = "root-redirect"
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "pinot_noir.authentication.GoogleOIDCAuthenticationBackend",
]

# Optional Google OpenID Connect login. User creation is deliberately disabled:
# Google must match one active existing user by verified email address.
OIDC_RP_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")
OIDC_RP_CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "")
OIDC_RP_SCOPES = "openid email"
OIDC_RP_SIGN_ALGO = "RS256"
OIDC_CREATE_USER = False
OIDC_USE_NONCE = True
OIDC_TIMEOUT = 10
OIDC_OP_AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
OIDC_OP_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
OIDC_OP_USER_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"
OIDC_OP_JWKS_ENDPOINT = "https://www.googleapis.com/oauth2/v3/certs"
LOGIN_REDIRECT_URL_FAILURE = "/login/?oauth=failed"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "pinot_noir" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "pinot_noir.authentication.google_oauth",
                "pinot_noir.pages.context_processors.nav_entries",
                "pinot_noir.pages.context_processors.vanilla_css",
                "pinot_noir.site_admin.context_processors.site_admin",
                "pinot_noir.user_settings.context_processors.user_settings",
                "pinot_noir.data_manager.context_processors.team",
            ],
        },
    },
]

WSGI_APPLICATION = "pinot_noir.wsgi.application"


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [
    BASE_DIR / "static",
]
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# django-tasks configuration
TASKS = {
    "default": {
        "BACKEND": "django_tasks_db.DatabaseBackend",
    }
}

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
