from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.test import TestCase
from django.urls import reverse
from ubq.models import BugRecord, BugSubmissionRecord

from pinot_noir.data_manager.models import (
    BackportBugFilterSettings,
    BackportBugPackageInfo,
    MergeBugFilterSettings,
    MergeBugPackageInfo,
    UserTokens,
)

from .models import UbuntuRelease


def _submission(bug_type: str = "merge") -> BugSubmissionRecord:
    package_names = ["testpkg"]
    return BugSubmissionRecord(
        provider_name="launchpad",
        title=f"{bug_type} testpkg",
        package_names=package_names,
        description="Prepared by the backend",
        tags=["server-todo"],
        milestone="ubuntu-25.11",
    )


def _bug(bug_id: str = "123") -> BugRecord:
    return BugRecord(provider_name="launchpad", id=bug_id, title="Submitted bug")


class NewBugViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="secret")
        self.tokens = UserTokens.objects.create(user=self.user, lp_token="alice-token")
        self.client.force_login(self.user)
        self.release = UbuntuRelease.objects.create(
            adjective="resolute",
            animal="raccoon",
            version="26.04",
            status=UbuntuRelease.STATUS_DEVEL,
        )
        self.merge_filter = MergeBugFilterSettings.objects.create(
            site=Site.objects.get_current(),
            settings_type=MergeBugFilterSettings.TYPE_MERGE,
            tags=["server-todo"],
        )
        self.merge_package = MergeBugPackageInfo.objects.create(package="testpkg")

    def url(self, bug_type: str) -> str:
        return reverse("launchpad-mergebug", kwargs={"bug_type": bug_type})

    @patch("pinot_noir.launchpad.views.get_launchpad_service_for_user")
    def test_anonymous_user_is_redirected_to_login(self, get_service_mock):
        self.client.logout()

        response = self.client.post(self.url("merge"), {"package": "testpkg"})

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])
        get_service_mock.assert_not_called()

    @patch("pinot_noir.launchpad.views.get_launchpad_service_for_user")
    def test_user_without_launchpad_token_cannot_submit(self, get_service_mock):
        self.tokens.delete()

        response = self.client.post(self.url("merge"), {"package": "testpkg"})

        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "Add a Launchpad token in Settings", status_code=403)
        get_service_mock.assert_not_called()

    def test_only_post_is_allowed(self):
        response = self.client.get(self.url("merge"))

        self.assertEqual(response.status_code, 405)

    @patch("pinot_noir.launchpad.views.get_launchpad_service_for_user")
    def test_unknown_bug_type_is_rejected(self, get_service_mock):
        response = self.client.post(self.url("other"), {"package": "testpkg"})

        self.assertEqual(response.status_code, 400)
        get_service_mock.assert_not_called()

    @patch("pinot_noir.launchpad.views.get_launchpad_service_for_user")
    def test_blank_package_is_rejected(self, get_service_mock):
        response = self.client.post(self.url("merge"), {"package": "  "})

        self.assertEqual(response.status_code, 400)
        get_service_mock.assert_not_called()

    @patch("pinot_noir.launchpad.bug_submission.prepare_merge_bug")
    @patch("pinot_noir.launchpad.views.get_launchpad_service_for_user")
    def test_merge_uses_backend_preparation_and_logged_in_users_token(
        self, get_service_mock, prepare_mock
    ):
        service = MagicMock()
        service.submit_bug.return_value = _bug()
        get_service_mock.return_value = service
        prepare_mock.return_value = _submission()

        response = self.client.post(
            self.url("merge"),
            {"package": "testpkg", "milestone": "26.04", "assignee": "alice"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), "https://bugs.launchpad.net/bugs/123")
        get_service_mock.assert_called_once_with("alice")
        prepare_mock.assert_called_once()
        self.assertEqual(prepare_mock.call_args.kwargs["package_settings"], self.merge_package)
        self.assertEqual(prepare_mock.call_args.kwargs["filter_settings"], self.merge_filter)
        self.assertEqual(prepare_mock.call_args.kwargs["ubuntu_release"], self.release)

        submitted = service.submit_bug.call_args.kwargs["submission"]
        self.assertEqual(submitted.description, "Prepared by the backend")
        self.assertEqual(submitted.tags, ["server-todo"])
        self.assertEqual(submitted.milestone, "ubuntu-26.04")
        self.assertEqual(submitted.assignee.username, "alice")
        self.merge_package.refresh_from_db()
        self.assertTrue(self.merge_package.bug_filed_this_cycle)

    @patch("pinot_noir.launchpad.bug_submission.prepare_backport_bug")
    @patch("pinot_noir.launchpad.views.get_launchpad_service_for_user")
    def test_backport_uses_backend_preparation(self, get_service_mock, prepare_mock):
        BackportBugFilterSettings.objects.create(
            site=Site.objects.get_current(),
            settings_type=MergeBugFilterSettings.TYPE_BACKPORT,
            tags=["server-todo"],
        )
        package = BackportBugPackageInfo.objects.create(
            name="testpkg",
            package_names_combined="testpkg",
            description_template="Backport description",
        )
        service = MagicMock()
        service.submit_bug.return_value = _bug("456")
        get_service_mock.return_value = service
        prepare_mock.return_value = _submission("backport")

        response = self.client.post(
            self.url("backport"),
            {"package": "testpkg", "milestone": "26.03", "assignee": "bob"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), "https://bugs.launchpad.net/bugs/456")
        self.assertEqual(prepare_mock.call_args.kwargs["package_settings"], package)
        submitted = service.submit_bug.call_args.kwargs["submission"]
        self.assertEqual(submitted.milestone, "ubuntu-26.03")
        self.assertEqual(submitted.assignee.username, "bob")
        package.refresh_from_db()
        self.assertTrue(package.bug_filed_this_cycle)

    @patch("pinot_noir.launchpad.bug_submission.prepare_merge_bug")
    @patch("pinot_noir.launchpad.views.get_launchpad_service_for_user")
    def test_no_prepared_submission_does_not_call_launchpad(self, get_service_mock, prepare_mock):
        service = MagicMock()
        get_service_mock.return_value = service
        prepare_mock.return_value = None

        response = self.client.post(self.url("merge"), {"package": "testpkg"})

        self.assertEqual(response.status_code, 409)
        service.submit_bug.assert_not_called()
        self.merge_package.refresh_from_db()
        self.assertFalse(self.merge_package.bug_filed_this_cycle)

    @patch("pinot_noir.launchpad.bug_submission.prepare_merge_bug")
    @patch("pinot_noir.launchpad.views.get_launchpad_service_for_user")
    def test_launchpad_rejection_is_reported(self, get_service_mock, prepare_mock):
        service = MagicMock()
        service.submit_bug.return_value = None
        get_service_mock.return_value = service
        prepare_mock.return_value = _submission()

        response = self.client.post(self.url("merge"), {"package": "testpkg"})

        self.assertEqual(response.status_code, 502)
        self.merge_package.refresh_from_db()
        self.assertFalse(self.merge_package.bug_filed_this_cycle)
