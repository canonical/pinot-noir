from unittest.mock import MagicMock

from django.test import SimpleTestCase

from pinot_noir.data_manager.helpers import MergePackageVersionInfo, prepare_merge_bug

_INTRO_LINE = "A new release of testpkg is available for merging from Debian.\n\n"


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
        self.assertEqual(
            str(info),
            "A new release of testpkg is available for merging from Debian.\n\n"
            "Ubuntu: 1.2.3-0ubuntu1\n"
            "Debian Unstable: 1.2.4-1\n",
        )

    def test_str_with_proposed(self):
        info = _make_info(proposed="1.2.3-1ubuntu1", release="1.2.3-0ubuntu1", unstable="1.2.4-1")
        self.assertEqual(
            str(info),
            "A new release of testpkg is available for merging from Debian.\n\n"
            "Ubuntu Proposed: 1.2.3-1ubuntu1\n"
            "Debian Unstable: 1.2.4-1\n",
        )

    def test_str_with_experimental(self):
        info = _make_info(release="1.2.3-0ubuntu1", unstable="1.2.3-1", experimental="1.2.4-1")
        self.assertEqual(
            str(info),
            "A new release of testpkg is available for merging from Debian.\n\n"
            "Ubuntu: 1.2.3-0ubuntu1\n"
            "Debian Experimental: 1.2.4-1\n"
            "Debian Unstable: 1.2.3-1\n",
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
            "A new release of testpkg is available for merging from Debian.\n\n"
            "Ubuntu Proposed: 1.2.3-1ubuntu1\n"
            "Debian Experimental: 1.2.4-1\n"
            "Debian Unstable: 1.2.3-1\n",
        )

    def test_str_no_proposed_when_release_is_newer(self):
        """Proposed version older than release should not appear in the string."""
        info = _make_info(proposed="1.2.2-1", release="1.2.3-0ubuntu1", unstable="1.2.4-1")
        self.assertIn("Ubuntu: 1.2.3-0ubuntu1", str(info))
        self.assertNotIn("Proposed", str(info))


# ---------------------------------------------------------------------------
# Helpers for prepare_merge_bug tests
# ---------------------------------------------------------------------------


def _make_release(version: str = "26.04", adjective: str = "resolute") -> MagicMock:
    m = MagicMock()
    m.version = version
    m.adjective = adjective
    return m


def _make_package_settings(
    package: str = "testpkg",
    bug_filed: bool = False,
    offset: int = 0,
) -> MagicMock:
    m = MagicMock()
    m.package = package
    m.bug_filed_this_cycle = bug_filed
    m.milestone_offset = offset
    return m


def _make_filter_settings(
    tags: list[str] | None = None,
    subscribers: list[str] | None = None,
) -> MagicMock:
    m = MagicMock()
    m.tags = tags if tags is not None else ["server-todo"]
    m.subscribers = subscribers if subscribers is not None else ["ubuntu-server"]
    return m


def _make_merge_service(
    release_mock: MagicMock,
    proposed: str = "",
    release_ver: str = "",
    unstable: str = "",
    experimental: str = "",
) -> MagicMock:
    """Return a mocked QueryService serving the given package versions."""
    versions = {
        (release_mock.adjective, "Proposed"): _mock_version(proposed),
        (release_mock.adjective, "Release"): _mock_version(release_ver),
        ("debian-unstable", None): _mock_version(unstable),
        ("debian-experimental", None): _mock_version(experimental),
    }
    service = MagicMock()
    service.get_version.side_effect = lambda pkg, series, pocket=None, provider_name=None: (
        versions.get((series, pocket))
    )
    return service


def _ready_result(offset: int = 0, version: str = "26.04"):
    """Return a prepare_merge_bug result for a ready-to-merge package."""
    release = _make_release(version=version)
    service = _make_merge_service(release, release_ver="1.2.3-0ubuntu1", unstable="1.2.4-1")
    return prepare_merge_bug(
        service, release, _make_package_settings(offset=offset), _make_filter_settings()
    )


class PrepareMergeBugTests(SimpleTestCase):
    def test_returns_none_when_bug_already_filed(self):
        release = _make_release()
        service = MagicMock()
        result = prepare_merge_bug(
            service,
            release,
            _make_package_settings(bug_filed=True),
            _make_filter_settings(),
        )
        self.assertIsNone(result)
        service.get_version.assert_not_called()

    def test_returns_none_when_not_ready_for_merge(self):
        release = _make_release()
        service = _make_merge_service(release, release_ver="1.2.4-0ubuntu1", unstable="1.2.3-1")
        result = prepare_merge_bug(
            service, release, _make_package_settings(), _make_filter_settings()
        )
        self.assertIsNone(result)

    def test_title_contains_package_and_adjective(self):
        result = _ready_result()
        self.assertIsNotNone(result)
        self.assertEqual(result.title, "Merge testpkg from Debian for resolute cycle")

    def test_description_starts_with_intro_line(self):
        result = _ready_result()
        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(result.description.startswith(_INTRO_LINE))

    def test_tags_passed_through(self):
        release = _make_release()
        service = _make_merge_service(release, release_ver="1.2.3-0ubuntu1", unstable="1.2.4-1")
        result = prepare_merge_bug(
            service,
            release,
            _make_package_settings(),
            _make_filter_settings(tags=["server-todo", "merge"]),
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.tags, ["server-todo", "merge"])

    def test_subscribers_passed_through(self):
        release = _make_release()
        service = _make_merge_service(release, release_ver="1.2.3-0ubuntu1", unstable="1.2.4-1")
        result = prepare_merge_bug(
            service,
            release,
            _make_package_settings(),
            _make_filter_settings(subscribers=["ubuntu-server", "ubuntu-mir-team"]),
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(
            [s.username for s in result.subscribers],
            ["ubuntu-server", "ubuntu-mir-team"],
        )

    def test_milestone_offset_zero_uses_earliest(self):
        # sorted milestones for 26.04: ["25.11", "25.12", "26.01", "26.02", "26.03", "26.04"]
        result = _ready_result(offset=0, version="26.04")
        self.assertIsNotNone(result)
        self.assertEqual(result.milestone, "ubuntu-25.11")

    def test_milestone_with_nonzero_offset(self):
        result = _ready_result(offset=2, version="26.04")
        self.assertIsNotNone(result)
        self.assertEqual(result.milestone, "ubuntu-26.01")

    def test_milestone_offset_out_of_range_uses_earliest(self):
        result = _ready_result(offset=10, version="26.04")
        self.assertIsNotNone(result)
        self.assertEqual(result.milestone, "ubuntu-25.11")
