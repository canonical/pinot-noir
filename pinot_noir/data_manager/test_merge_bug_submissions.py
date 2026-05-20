from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.test import TestCase
from ubq.models import BugSubmissionRecord, UserRecord

from pinot_noir.data_manager.models import MergeBugFilterSettings, MergeBugPackageInfo, UserTokens
from pinot_noir.data_manager.tasks import (
    bug_submission_from_json_dict,
    bug_submission_to_json_dict,
    prepare_merge_bug_submissions,
    submit_prepared_merge_bug_submissions,
)
from pinot_noir.launchpad.models import UbuntuRelease


class MergeBugSubmissionConversionTests(TestCase):
    def test_bug_submission_json_round_trip(self):
        submission = BugSubmissionRecord(
            provider_name="launchpad",
            title="Merge pkg from Debian for resolute cycle",
            package_names=["pkg"],
            description="desc",
            tags=["server-todo"],
            subscribers=[UserRecord(username="ubuntu-server")],
            assignee=UserRecord(username="owner"),
            private=False,
            milestone="ubuntu-26.04",
        )

        serialized = bug_submission_to_json_dict(submission)
        round_tripped = bug_submission_from_json_dict(serialized)

        self.assertEqual(round_tripped.provider_name, submission.provider_name)
        self.assertEqual(round_tripped.title, submission.title)
        self.assertEqual(round_tripped.package_names, submission.package_names)
        self.assertEqual(round_tripped.tags, submission.tags)
        self.assertEqual(round_tripped.milestone, submission.milestone)
        self.assertEqual(round_tripped.assignee.username, "owner")
        self.assertEqual([sub.username for sub in round_tripped.subscribers], ["ubuntu-server"])


class MergeBugSubmissionPreparationTests(TestCase):
    @patch("pinot_noir.data_manager.tasks.prepare_merge_bugs_for_all_packages")
    @patch("pinot_noir.data_manager.tasks._get_launchpad_service_for_user")
    def test_prepare_uses_active_users_token_and_all_packages(
        self, get_service_mock, prepare_all_mock
    ):
        user = User.objects.create_user(username="alice", password="pw")
        UserTokens.objects.create(user=user, lp_token="alice-token")

        site = Site.objects.get_current()
        MergeBugFilterSettings.objects.create(
            site=site,
            settings_type=MergeBugFilterSettings.TYPE_MERGE,
            tags_combined="server-todo",
            subscribers_combined="ubuntu-server",
        )
        UbuntuRelease.objects.create(
            adjective="resolute",
            animal="raccoon",
            version="26.04",
            status=UbuntuRelease.STATUS_DEVEL,
        )

        expected = [("pkg", MagicMock())]
        prepare_all_mock.return_value = expected

        result = prepare_merge_bug_submissions(user)

        self.assertEqual(result, expected)
        get_service_mock.assert_called_once_with(user)
        prepare_all_mock.assert_called_once()


class MergeBugSubmissionSubmitTests(TestCase):
    @patch("pinot_noir.data_manager.tasks._get_launchpad_service_for_user")
    def test_submit_marks_successful_packages_filed(self, get_service_mock):
        user = User.objects.create_user(username="alice", password="pw")
        UserTokens.objects.create(user=user, lp_token="alice-token")

        pkg_ok = MergeBugPackageInfo.objects.create(package="okpkg")
        pkg_fail = MergeBugPackageInfo.objects.create(package="failpkg")

        submit_ok = BugSubmissionRecord(
            provider_name="launchpad",
            title="t1",
            package_names=["okpkg"],
            tags=[],
            subscribers=[],
            private=False,
        )
        submit_fail = BugSubmissionRecord(
            provider_name="launchpad",
            title="t2",
            package_names=["failpkg"],
            tags=[],
            subscribers=[],
            private=False,
        )

        service = MagicMock()
        service.submit_bug.side_effect = [object(), None]
        get_service_mock.return_value = service

        submitted, failed = submit_prepared_merge_bug_submissions(
            user,
            [("okpkg", submit_ok), ("failpkg", submit_fail)],
        )

        self.assertEqual((submitted, failed), (1, 1))
        pkg_ok.refresh_from_db()
        pkg_fail.refresh_from_db()
        self.assertTrue(pkg_ok.bug_filed_this_cycle)
        self.assertFalse(pkg_fail.bug_filed_this_cycle)
