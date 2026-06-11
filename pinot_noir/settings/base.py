"""
Base Django settings for pinot_noir project.

Common settings shared across all environments.
"""

from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent
SITE_ID = 1


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.sites",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_tasks",
    "django_tasks_db",
    # Pinot Noir base applications
    "pinot_noir.launchpad",
    "pinot_noir.data_manager",
    "pinot_noir.pages",
    # Pinot Noir web page applications
    "pinot_noir.merges_schedule",
    "pinot_noir.reviews",
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
                "pinot_noir.pages.context_processors.nav_entries",
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
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# django-tasks configuration
TASKS = {
    "default": {
        "BACKEND": "django_tasks_db.DatabaseBackend",
    }
}

# Sidebar navigation. Add a new dict here when introducing a new data page.
# `slug` is the PageMetadata key for that page; `url_name` is a namespaced
# Django URL name resolved at request time.
PINOT_NOIR_NAV = [
    {
        "slug": "merges-schedule",
        "label": "Merge Schedule",
        "url_name": "merges_schedule:index",
        "icon": "circle-of-friends",
    },
    {
        "slug": "reviews",
        "label": "Reviews",
        "url_name": "reviews:index",
        "icon": "circle-of-friends",
    },
]

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
