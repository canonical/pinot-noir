import json
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.staticfiles.finders import get_finder, get_finders
from django.core.management import call_command
from django.test import SimpleTestCase, override_settings

from .context_processors import vanilla_css
from .management.commands.collectstatic import VANILLA_CSS, VANILLA_URL


class VanillaCSSURLTests(SimpleTestCase):
    def test_cdn_fallback_when_css_is_not_collected(self):
        with TemporaryDirectory() as static_root:
            with override_settings(STATIC_ROOT=static_root):
                self.assertEqual(vanilla_css(None)["vanilla_css_url"], VANILLA_URL)

    def test_cdn_in_debug_even_when_css_is_collected(self):
        with TemporaryDirectory() as static_root:
            with override_settings(STATIC_ROOT=static_root, DEBUG=True):
                css_path = Path(static_root, VANILLA_CSS)
                css_path.parent.mkdir(parents=True)
                css_path.write_bytes(b"body{color:#111}")
                self.assertEqual(vanilla_css(None)["vanilla_css_url"], VANILLA_URL)

    def test_local_url_when_css_is_collected(self):
        with TemporaryDirectory() as static_root:
            with override_settings(STATIC_ROOT=static_root, DEBUG=False):
                css_path = Path(static_root, VANILLA_CSS)
                css_path.parent.mkdir(parents=True)
                css_path.write_bytes(b"body{color:#111}")
                self.assertEqual(vanilla_css(None)["vanilla_css_url"], f"/static/{VANILLA_CSS}")


class CollectStaticTests(SimpleTestCase):
    @patch("pinot_noir.pages.management.commands.collectstatic.urlopen")
    def test_downloads_vanilla_css_for_collection(self, urlopen):
        css = b"body{color:#111}\n/*# sourceMappingURL=build.css.map */"
        collected_css = b"body{color:#111}"
        urlopen.return_value = BytesIO(css)

        with TemporaryDirectory() as static_root:
            with override_settings(
                DEBUG=False,
                STATIC_ROOT=static_root,
                STATICFILES_DIRS=[],
                STATICFILES_FINDERS=["django.contrib.staticfiles.finders.FileSystemFinder"],
                STORAGES={
                    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                    "staticfiles": {
                        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
                    },
                },
            ):
                # Management commands run system checks before handle(), caching finders.
                getattr(get_finder, "cache_clear")()
                list(get_finders())
                call_command("collectstatic", interactive=False, verbosity=0)

                static_root_path = Path(static_root)
                self.assertEqual((static_root_path / VANILLA_CSS).read_bytes(), collected_css)
                manifest = json.loads((static_root_path / "staticfiles.json").read_text())
                hashed_css = manifest["paths"][VANILLA_CSS]
                self.assertNotEqual(hashed_css, VANILLA_CSS)
                self.assertEqual((static_root_path / hashed_css).read_bytes(), collected_css)
                self.assertEqual(vanilla_css(None)["vanilla_css_url"], f"/static/{VANILLA_CSS}")

        urlopen.assert_called_once_with(VANILLA_URL, timeout=60)
