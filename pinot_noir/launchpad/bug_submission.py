from dataclasses import replace

from django.core.exceptions import ObjectDoesNotExist
from django.http import QueryDict
from ubq import QueryService
from ubq.models import BugSubmissionRecord, UserRecord

from pinot_noir.data_manager.bug_filing import prepare_backport_bug, prepare_merge_bug
from pinot_noir.data_manager.common import get_devel_or_requested_release
from pinot_noir.data_manager.models import (
    BackportBugFilterSettings,
    BackportBugPackageInfo,
    MergeBugFilterSettings,
    MergeBugPackageInfo,
)


class BugSubmission:
    """Prepare one merge or backport bug from the Merge Schedule form."""

    def __init__(self, post_data: QueryDict, bug_type: str):
        self._bug_type = bug_type
        self._package = post_data.get("package", "").strip()
        self._milestone = post_data.get("milestone", "").strip()
        self._assignee = post_data.get("assignee", "").strip()
        self._affected_releases = post_data.getlist("affected_releases")

    def to_dict(self) -> dict:
        """Convert submission data to dictionary."""
        return {
            "package": self._package,
            "milestone": self._milestone,
            "assignee": self._assignee,
            "bug_type": self._bug_type,
            "affected_releases": self._affected_releases,
        }

    def get_package_name(self) -> str:
        """Get the package name for the bug submission."""
        return self._package

    def get_milestone(self) -> str | None:
        """Get the selected Launchpad milestone, if one was specified."""
        if self._milestone:
            return f"ubuntu-{self._milestone}"
        return None

    def get_assignee(self) -> str | None:
        """Get the selected Launchpad assignee, if one was specified."""
        return self._assignee or None

    def get_affected_releases(self) -> list[str]:
        """Get the selected affected releases for a backport bug."""
        if self._bug_type == "backport":
            return self._affected_releases
        return []

    def _prepare_merge(self, service: QueryService) -> BugSubmissionRecord | None:
        filter_settings = MergeBugFilterSettings.objects.filter(
            settings_type=MergeBugFilterSettings.TYPE_MERGE
        ).first()
        if filter_settings is None:
            raise ObjectDoesNotExist("No merge bug filter settings found.")

        package_settings = MergeBugPackageInfo.objects.filter(package=self._package).first()
        if package_settings is None:
            package_settings = MergeBugPackageInfo(package=self._package)

        return prepare_merge_bug(
            queryService=service,
            ubuntu_release=get_devel_or_requested_release(),
            package_settings=package_settings,
            filter_settings=filter_settings,
        )

    def _prepare_backport(self) -> BugSubmissionRecord | None:
        filter_settings = BackportBugFilterSettings.objects.first()
        if filter_settings is None:
            raise ObjectDoesNotExist("No backport bug filter settings found.")

        package_settings = BackportBugPackageInfo.objects.filter(name=self._package).first()
        if package_settings is None:
            package_settings = BackportBugPackageInfo(
                name=self._package,
                package_names_combined=self._package,
            )

        return prepare_backport_bug(
            ubuntu_release=get_devel_or_requested_release(),
            package_settings=package_settings,
            filter_settings=filter_settings,
        )

    def prepare(self, service: QueryService) -> BugSubmissionRecord | None:
        """Prepare a bug through the standard merge/backport backend workflow."""
        if self._bug_type == "merge":
            submission = self._prepare_merge(service)
        elif self._bug_type == "backport":
            submission = self._prepare_backport()
        else:
            raise ValueError(f"Unknown bug type '{self._bug_type}'.")

        if submission is None:
            return None

        return replace(
            submission,
            milestone=self.get_milestone() or submission.milestone,
            assignee=(
                UserRecord(username=self._assignee) if self._assignee else submission.assignee
            ),
        )

    def mark_filed(self) -> None:
        """Mark a configured package as filed after Launchpad accepts the bug."""
        if self._bug_type == "merge":
            MergeBugPackageInfo.objects.filter(package=self._package).update(
                bug_filed_this_cycle=True
            )
        elif self._bug_type == "backport":
            BackportBugPackageInfo.objects.filter(name=self._package).update(
                bug_filed_this_cycle=True
            )
