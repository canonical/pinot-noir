from unittest.mock import MagicMock, call, patch

from django.test import SimpleTestCase

from .tasks import update_schedule_bug_filter


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
