from unittest.mock import MagicMock

from django.test import SimpleTestCase

from pinot_noir.data_manager.helpers import MergePackageVersionInfo


def _mock_version(version_string: str):
    """Return a mock version object, or None for an empty string."""
    if not version_string:
        return None
    m = MagicMock()
    m.version_string = version_string
    return m


def _make_info(
    proposed: str = "",
    release: str = "",
    unstable: str = "",
    experimental: str = "",
    devel_series: str = "devel",
) -> MergePackageVersionInfo:
    """Build a MergePackageVersionInfo with the given versions already loaded."""
    versions = {
        (devel_series, "Proposed"): _mock_version(proposed),
        (devel_series, "Release"): _mock_version(release),
        ("debian-unstable", None): _mock_version(unstable),
        ("debian-experimental", None): _mock_version(experimental),
    }
    service = MagicMock()
    service.get_version.side_effect = lambda pkg, series, pocket=None, provider_name=None: (
        versions.get((series, pocket))
    )
    info = MergePackageVersionInfo("testpkg", devel_series, service)
    info.refresh_versions()
    return info


class MergePackageVersionInfoReadyTests(SimpleTestCase):
    def test_ready_when_unstable_newer_than_release(self):
        info = _make_info(release="1.2.3-0ubuntu1", unstable="1.2.4-1")
        self.assertTrue(info.ready_for_merge())

    def test_not_ready_when_release_matches_unstable(self):
        info = _make_info(release="1.2.3-1", unstable="1.2.3-1")
        self.assertFalse(info.ready_for_merge())

    def test_not_ready_when_release_newer_than_unstable(self):
        info = _make_info(release="1.2.4-0ubuntu1", unstable="1.2.3-1")
        self.assertFalse(info.ready_for_merge())

    def test_ready_when_unstable_newer_than_proposed(self):
        info = _make_info(proposed="1.2.3-1ubuntu1", release="1.2.3-0ubuntu1", unstable="1.2.4-1")
        self.assertTrue(info.ready_for_merge())

    def test_not_ready_when_proposed_matches_unstable(self):
        info = _make_info(proposed="1.2.4-1", release="1.2.3-0ubuntu1", unstable="1.2.4-1")
        self.assertFalse(info.ready_for_merge())

    def test_not_ready_when_proposed_newer_than_unstable(self):
        info = _make_info(proposed="1.2.4-1ubuntu1", release="1.2.3-0ubuntu1", unstable="1.2.4-1")
        self.assertFalse(info.ready_for_merge())

    def test_ready_when_experimental_newer_than_release(self):
        info = _make_info(release="1.2.3-0ubuntu1", unstable="1.2.3-1", experimental="1.2.4-1")
        self.assertTrue(info.ready_for_merge())

    def test_ready_when_experimental_newer_than_proposed(self):
        info = _make_info(
            proposed="1.2.4-1ubuntu1",
            release="1.2.3-0ubuntu1",
            unstable="1.2.3-1",
            experimental="1.2.5-1",
        )
        self.assertTrue(info.ready_for_merge())

    def test_not_ready_when_proposed_ahead_of_experimental(self):
        info = _make_info(
            proposed="1.2.5-0ubuntu1",
            release="1.2.3-0ubuntu1",
            unstable="1.2.3-1",
            experimental="1.2.4-1",
        )
        self.assertFalse(info.ready_for_merge())

    def test_not_ready_when_all_versions_empty(self):
        info = _make_info()
        self.assertFalse(info.ready_for_merge())


class MergePackageVersionInfoStrTests(SimpleTestCase):
    def test_str_basic(self):
        info = _make_info(release="1.2.3-0ubuntu1", unstable="1.2.4-1")
        self.assertEqual(str(info), "Ubuntu: 1.2.3-0ubuntu1\nDebian Unstable: 1.2.4-1\n")

    def test_str_with_proposed(self):
        info = _make_info(proposed="1.2.3-1ubuntu1", release="1.2.3-0ubuntu1", unstable="1.2.4-1")
        self.assertEqual(str(info), "Ubuntu Proposed: 1.2.3-1ubuntu1\nDebian Unstable: 1.2.4-1\n")

    def test_str_with_experimental(self):
        info = _make_info(release="1.2.3-0ubuntu1", unstable="1.2.3-1", experimental="1.2.4-1")
        self.assertEqual(
            str(info),
            "Ubuntu: 1.2.3-0ubuntu1\nDebian Experimental: 1.2.4-1\nDebian Unstable: 1.2.3-1\n",
        )

    def test_str_with_proposed_and_experimental(self):
        info = _make_info(
            proposed="1.2.3-1ubuntu1",
            release="1.2.3-0ubuntu1",
            unstable="1.2.3-1",
            experimental="1.2.4-1",
        )
        self.assertEqual(
            str(info),
            "Ubuntu Proposed: 1.2.3-1ubuntu1\n"
            "Debian Experimental: 1.2.4-1\n"
            "Debian Unstable: 1.2.3-1\n",
        )

    def test_str_no_proposed_when_release_is_newer(self):
        """Proposed version older than release should not appear in the string."""
        info = _make_info(proposed="1.2.2-1", release="1.2.3-0ubuntu1", unstable="1.2.4-1")
        self.assertIn("Ubuntu: 1.2.3-0ubuntu1", str(info))
        self.assertNotIn("Proposed", str(info))
