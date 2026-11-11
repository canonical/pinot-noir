"""Collect static files, downloading pinned third-party assets first."""

import tempfile
from pathlib import Path
from urllib.request import urlopen

from django.conf import settings
from django.contrib.staticfiles.finders import get_finder
from django.contrib.staticfiles.management.commands.collectstatic import (
    Command as CollectStaticCommand,
)
from django.core.management.base import CommandError

VANILLA_VERSION = "4.59.0"
VANILLA_CSS = f"css/vanilla_framework_version_{VANILLA_VERSION}.min.css"
VANILLA_URL = f"https://assets.ubuntu.com/v1/vanilla_framework_version_{VANILLA_VERSION}.min.css"


class Command(CollectStaticCommand):
    help = "Collect static files, including the pinned Vanilla CSS release."

    def handle(self, *args, **options) -> str | None:
        with tempfile.TemporaryDirectory(prefix="pinot-noir-static-") as static_dir:
            css_path = Path(static_dir, VANILLA_CSS)
            css_path.parent.mkdir(parents=True)
            try:
                with urlopen(VANILLA_URL, timeout=60) as response:
                    css = response.read()
                # The CDN does not publish this developer-only source map.
                css_path.write_bytes(css.replace(b"\n/*# sourceMappingURL=build.css.map */", b""))
            except OSError as exc:
                message = f"Could not download Vanilla CSS from {VANILLA_URL}: {exc}"
                raise CommandError(message) from exc

            original_staticfiles_dirs = settings.STATICFILES_DIRS
            settings.STATICFILES_DIRS = [*original_staticfiles_dirs, static_dir]
            # System checks initialise the finders before handle() runs.
            getattr(get_finder, "cache_clear")()
            try:
                return super().handle(*args, **options)
            finally:
                settings.STATICFILES_DIRS = original_staticfiles_dirs
                getattr(get_finder, "cache_clear")()
