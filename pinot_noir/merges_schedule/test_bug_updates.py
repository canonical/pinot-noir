from unittest.mock import MagicMock, call, patch

from django.test import SimpleTestCase, TestCase
from ubq.models import BugRecord, BugTaskRecord

from pinot_noir.launchpad.models import UbuntuRelease

from .models import Merge
from .tasks import refresh_single_merge, update_schedule_bug_filter


@patch("pinot_noir.merges_schedule.tasks.get_launchpad_for_user")
class UpdateScheduleBugFilterTests(SimpleTestCase):
    def test_tags_add_current_and_remove_only_deleted_managed_entries(self, get_launchpad):
        launchpad = MagicMock()
        get_launchpad.return_value = launchpad
        first = MagicMock()
        first.tags = ["unrelated", "old", "keep"]
        second = MagicMock()
        second.tags = ["keep", "new", "other"]
        launchpad.bugs.__getitem__.side_effect = lambda bug_id: {
            "1": first,
            "2": second,
        }[bug_id]

        update_schedule_bug_filter.call(
            username="alice",
            field="tags",
            previous_values=["old", "keep"],
            values=["keep", "new"],
            bug_ids=[1, 2],
        )

        self.assertEqual(first.tags, ["keep", "new", "unrelated"])
        first.lp_save.assert_called_once_with()
        second.lp_save.assert_not_called()
        get_launchpad.assert_called_once_with("alice")

    def test_subscribers_remove_deleted_and_subscribe_all_current(self, get_launchpad):
        launchpad = MagicMock()
        get_launchpad.return_value = launchpad
        people = {name: MagicMock() for name in ("old", "keep", "new")}
        launchpad.people.__getitem__.side_effect = people.__getitem__
        bug = MagicMock()
        launchpad.bugs.__getitem__.return_value = bug

        update_schedule_bug_filter.call(
            username="alice",
            field="subscribers",
            previous_values=["old", "keep"],
            values=["keep", "new"],
            bug_ids=[1],
        )

        bug.unsubscribe.assert_called_once_with(person=people["old"])
        self.assertEqual(
            bug.subscribe.call_args_list,
            [call(person=people["keep"]), call(person=people["new"])],
        )
        bug.lp_save.assert_not_called()

    def test_no_bug_ids_does_not_authenticate(self, get_launchpad):
        update_schedule_bug_filter.call(
            username="alice",
            field="tags",
            previous_values=["old"],
            values=["new"],
            bug_ids=[],
        )
        get_launchpad.assert_not_called()

    def test_rejects_unknown_field(self, get_launchpad):
        with self.assertRaisesRegex(ValueError, "Unknown bug filter field"):
            update_schedule_bug_filter.call(
                username="alice",
                field="assignee",
                previous_values=[],
                values=[],
                bug_ids=[1],
            )
        get_launchpad.assert_not_called()

    def test_updates_other_bugs_then_reports_failures(self, get_launchpad):
        launchpad = MagicMock()
        get_launchpad.return_value = launchpad
        failing = MagicMock()
        failing.tags = ["old"]
        failing.lp_save.side_effect = RuntimeError("Launchpad failed")
        working = MagicMock()
        working.tags = ["old"]
        launchpad.bugs.__getitem__.side_effect = lambda bug_id: {
            "1": failing,
            "2": working,
        }[bug_id]

        with self.assertLogs("pinot_noir.merges_schedule.tasks", level="ERROR"):
            with self.assertRaisesRegex(RuntimeError, "Launchpad bugs: 1"):
                update_schedule_bug_filter.call(
                    username="alice",
                    field="tags",
                    previous_values=["old"],
                    values=["new"],
                    bug_ids=[1, 2],
                )

        self.assertEqual(working.tags, ["new"])
        working.lp_save.assert_called_once_with()


@patch("pinot_noir.merges_schedule.tasks.get_launchpad_for_user")
@patch("pinot_noir.merges_schedule.tasks.get_launchpad_service_for_user")
class RefreshSingleMergeVersionTests(TestCase):
    def setUp(self):
        UbuntuRelease.objects.create(
            adjective="resolute",
            animal="Raccoon",
            status=UbuntuRelease.STATUS_DEVEL,
        )
        Merge.objects.create(
            lp_bug=1,
            package="testpkg",
            merge_type=Merge.TYPE_MERGE,
            status=Merge.STATUS_NEW,
        )

    @staticmethod
    def _bug(title: str, status: str = "New") -> BugRecord:
        return BugRecord(
            provider_name="launchpad",
            id="1",
            title=title,
            description="Old description",
            bug_tasks=[
                BugTaskRecord(
                    title="testpkg in Ubuntu",
                    package_name="testpkg",
                    status=status,
                )
            ],
        )

    @staticmethod
    def _service(
        bug: BugRecord,
        release: str = "1.2.3-0ubuntu1",
        unstable: str = "1.2.4-1",
        experimental: str = "",
    ) -> MagicMock:
        versions: dict[tuple[str | None, str | None, str | None], MagicMock | None] = {
            ("ubuntu", "resolute", "Proposed"): None,
            ("ubuntu", "resolute", "Release"): MagicMock(version_string=release),
            ("debian", "sid", "Release"): (
                MagicMock(version_string=unstable) if unstable else None
            ),
            ("debian", "experimental", "Release"): (
                MagicMock(version_string=experimental) if experimental else None
            ),
        }

        def get_version(package, archive=None, series=None, pocket=None, provider_name=None):
            return versions.get((archive, series, pocket))

        service = MagicMock()
        service.get_bug.return_value = bug
        service.get_version.side_effect = get_version
        return service

    def test_updates_outdated_title_and_description(self, get_service, get_launchpad):
        title = "Merge testpkg 1.2.3-1 from Debian for resolute cycle"
        get_service.return_value = self._service(self._bug(title))
        lp_bug = MagicMock()
        get_launchpad.return_value.bugs.__getitem__.return_value = lp_bug

        refresh_single_merge.call("alice", 1)

        self.assertEqual(lp_bug.title, "Merge testpkg 1.2.4-1 from Debian for resolute cycle")
        self.assertEqual(
            lp_bug.description,
            "A new release of testpkg is available for merging from Debian.\n\n"
            "Ubuntu: 1.2.3-0ubuntu1\n"
            "Debian Unstable: 1.2.4-1\n",
        )
        lp_bug.lp_save.assert_called_once_with()
        get_launchpad.assert_called_once_with("alice")
        get_launchpad.return_value.bugs.__getitem__.assert_called_once_with("1")
        self.assertEqual(Merge.objects.get(lp_bug=1).status, Merge.STATUS_NEW)

    def test_uses_newer_experimental_version(self, get_service, get_launchpad):
        title = "Merge testpkg 1.2.3-1 from Debian for resolute cycle"
        get_service.return_value = self._service(self._bug(title), experimental="1.2.5-1")
        lp_bug = MagicMock()
        get_launchpad.return_value.bugs.__getitem__.return_value = lp_bug

        refresh_single_merge.call("alice", 1)

        self.assertEqual(lp_bug.title, "Merge testpkg 1.2.5-1 from Debian for resolute cycle")
        self.assertIn("Debian Experimental: 1.2.5-1\n", lp_bug.description)
        self.assertIn("Debian Unstable: 1.2.4-1\n", lp_bug.description)
        lp_bug.lp_save.assert_called_once_with()

    def test_leaves_current_version_unchanged(self, get_service, get_launchpad):
        title = "Merge testpkg 1.2.4-1 from Debian for resolute cycle"
        service = self._service(self._bug(title))
        get_service.return_value = service

        refresh_single_merge.call("alice", 1)

        self.assertEqual(service.get_version.call_count, 4)
        get_launchpad.assert_not_called()

    def test_does_not_downgrade_newer_title_version(self, get_service, get_launchpad):
        title = "Merge testpkg 1.2.5-1 from Debian for resolute cycle"
        get_service.return_value = self._service(self._bug(title))

        refresh_single_merge.call("alice", 1)

        get_launchpad.assert_not_called()

    def test_ignores_custom_title(self, get_service, get_launchpad):
        service = self._service(self._bug("Merge testpkg when time permits"))
        get_service.return_value = service

        refresh_single_merge.call("alice", 1)

        service.get_version.assert_not_called()
        get_launchpad.assert_not_called()

    def test_ignores_title_for_another_cycle(self, get_service, get_launchpad):
        title = "Merge testpkg 1.2.3-1 from Debian for noble cycle"
        service = self._service(self._bug(title))
        get_service.return_value = service

        refresh_single_merge.call("alice", 1)

        service.get_version.assert_not_called()
        get_launchpad.assert_not_called()

    def test_ignores_merge_no_longer_new(self, get_service, get_launchpad):
        title = "Merge testpkg 1.2.3-1 from Debian for resolute cycle"
        service = self._service(self._bug(title, status="In Progress"))
        get_service.return_value = service

        refresh_single_merge.call("alice", 1)

        service.get_version.assert_not_called()
        get_launchpad.assert_not_called()
        self.assertEqual(Merge.objects.get(lp_bug=1).status, Merge.STATUS_STARTED)
