"""Periodic data-refresh tasks for the data_manager application."""

from datetime import timedelta
from typing import Any

from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone
from django_tasks import task
from ubq import QueryService
from ubq.models import BugSubmissionRecord, ProviderCredentials, UserRecord

from pinot_noir.data_manager.helpers import (
    LP_STATUS_MAP,
    collect_bugs_for_type,
    merge_from_bug,
    milestones_for_release,
    package_from_url,
    prepare_merge_bugs_for_all_packages,
    release_from_branch,
)
from pinot_noir.data_manager.models import (
    BackportBugFilterSettings,
    LPReviewMarkerUser,
    MergeBugFilterSettings,
    MergeBugPackageInfo,
    UserTokens,
)
from pinot_noir.launchpad.models import LPUser, UbuntuRelease
from pinot_noir.merges_schedule.models import Merge
from pinot_noir.reviews.models import Review

REFRESH_INTERVAL_HOURS = 6


def _get_devel_release() -> UbuntuRelease:
    release = UbuntuRelease.objects.filter(status=UbuntuRelease.STATUS_DEVEL).first()
    if release is None:
        raise ObjectDoesNotExist("No Ubuntu development release found.")
    return release


def _get_launchpad_service_for_user(user: User) -> QueryService:
    tokens = UserTokens.objects.filter(user=user).first()
    if tokens is None or not tokens.lp_token:
        raise ObjectDoesNotExist(f"No Launchpad token configured for user '{user.username}'.")

    service = QueryService()
    service.login(
        provider_name="launchpad",
        credentials=ProviderCredentials(token=tokens.lp_token),
    )
    return service


def bug_submission_to_json_dict(submission: BugSubmissionRecord) -> dict[str, Any]:
    """Convert a BugSubmissionRecord into a JSON-safe dictionary."""
    return {
        "provider_name": submission.provider_name,
        "title": submission.title,
        "package_names": submission.package_names,
        "description": submission.description,
        "importance": submission.importance,
        "status": submission.status,
        "tags": submission.tags,
        "subscribers": [sub.username for sub in submission.subscribers],
        "assignee": submission.assignee.username if submission.assignee else None,
        "private": submission.private,
        "milestone": submission.milestone,
    }


def bug_submission_from_json_dict(data: dict[str, Any]) -> BugSubmissionRecord:
    """Build a BugSubmissionRecord from JSON-loaded dictionary data."""
    subscribers = [UserRecord(username=username) for username in data.get("subscribers", [])]
    assignee_name = data.get("assignee")
    assignee = UserRecord(username=assignee_name) if assignee_name else None

    return BugSubmissionRecord(
        provider_name=data["provider_name"],
        title=data["title"],
        package_names=data.get("package_names", []),
        description=data.get("description"),
        importance=data.get("importance"),
        status=data.get("status"),
        tags=data.get("tags", []),
        subscribers=subscribers,
        assignee=assignee,
        private=bool(data.get("private", False)),
        milestone=data.get("milestone"),
    )


def prepare_merge_bug_submissions(
    user: User,
    release_adjective: str | None = None,
) -> list[tuple[str, BugSubmissionRecord]]:
    """Prepare merge bug submissions for all packages using a user's LP token."""
    if release_adjective:
        ubuntu_release = UbuntuRelease.objects.get(adjective=release_adjective)
    else:
        ubuntu_release = _get_devel_release()

    filter_settings = MergeBugFilterSettings.objects.filter(
        settings_type=MergeBugFilterSettings.TYPE_MERGE
    ).first()
    if filter_settings is None:
        raise ObjectDoesNotExist("No merge bug filter settings found.")

    service = _get_launchpad_service_for_user(user)
    return prepare_merge_bugs_for_all_packages(service, ubuntu_release, filter_settings)


def submit_prepared_merge_bug_submissions(
    user: User,
    submissions: list[tuple[str, BugSubmissionRecord]],
) -> tuple[int, int]:
    """Submit prepared merge bug submissions and mark package rows as filed.

    Returns ``(submitted_count, failed_count)``.
    """
    service = _get_launchpad_service_for_user(user)

    submitted_count = 0
    failed_count = 0
    for package_name, submission in submissions:
        bug = service.submit_bug(submission=submission, provider_name="launchpad")
        if bug is None:
            failed_count += 1
            continue

        MergeBugPackageInfo.objects.filter(package=package_name).update(bug_filed_this_cycle=True)
        submitted_count += 1

    return submitted_count, failed_count


@task()
def refresh_merge_schedule(user: User, release_adjective: str) -> None:
    """Wipe the merge schedule then re-import bugs from Launchpad for a given Ubuntu release.

    Looks up the Ubuntu release by its adjective (e.g. ``'resolute'``), computes
    the six monthly milestones for that release cycle, then queries Launchpad for
    all bugs whose tags match ``MergeBugFilterSettings`` or
    ``BackportBugFilterSettings`` and whose milestone falls within that range.
    The ``Merge`` table is atomically replaced with the imported results.
    """
    try:
        release = UbuntuRelease.objects.get(adjective=release_adjective)
    except UbuntuRelease.DoesNotExist:
        return

    valid_milestones = milestones_for_release(release.version)
    merge_settings = MergeBugFilterSettings.objects.filter(
        settings_type=MergeBugFilterSettings.TYPE_MERGE
    ).first()
    backport_settings = BackportBugFilterSettings.objects.first()

    service = _get_launchpad_service_for_user(user)

    bugs_to_import: dict[str, tuple] = {}
    if merge_settings:
        collect_bugs_for_type(
            service, merge_settings, valid_milestones, Merge.TYPE_MERGE, bugs_to_import
        )
    if backport_settings:
        collect_bugs_for_type(
            service, backport_settings, valid_milestones, Merge.TYPE_BACKPORT, bugs_to_import
        )

    new_merges: list[Merge] = []
    for bug_id, (bug_record, milestone, merge_type) in bugs_to_import.items():
        full_bug = service.get_bug(bug_id, provider_name="launchpad")
        if full_bug is None:
            continue
        merge = merge_from_bug(bug_id, full_bug, milestone, merge_type)
        if merge is not None:
            new_merges.append(merge)

    Merge.objects.all().delete()
    Merge.objects.bulk_create(new_merges)


@task()
def refresh_reviews(user: User) -> None:
    """Replace the reviews table with current merge request data from Launchpad.

    Iterates over all stored LPUser records, queries Launchpad for each user's
    open merge proposals via ubq, then atomically replaces the contents of the
    reviews table.  After completion the task re-enqueues itself to run again
    after ``REFRESH_INTERVAL_HOURS`` hours.
    """

    service = _get_launchpad_service_for_user(user)

    marker_usernames = set(LPReviewMarkerUser.objects.values_list("username", flat=True))

    new_reviews: list[Review] = []
    for lp_user in LPUser.objects.all():
        merge_requests = service.get_merge_requests_from_user(
            user_id=lp_user.username,
            provider_name="launchpad",
        )
        for mr in merge_requests:
            package = package_from_url(mr.web_url or "")
            release_version = release_from_branch(mr.target_branch)
            status = LP_STATUS_MAP.get(mr.status or "", Review.STATUS_NEEDS_REVIEW)

            reviewer_username = ""
            reviewer_user = None
            if mr.assignees and any(a.username in marker_usernames for a in mr.assignees):
                for assignee in mr.assignees:
                    matched_lp_user = LPUser.objects.filter(username=assignee.username).first()
                    if matched_lp_user:
                        reviewer_username = assignee.username
                        reviewer_user = matched_lp_user
                        break

                new_reviews.append(
                    Review(
                        package=package,
                        release_version=release_version,
                        mp_url=mr.web_url or "",
                        reviewer=reviewer_username,
                        reviewer_user=reviewer_user,
                        submitter=lp_user.username,
                        submitter_user=lp_user,
                        status=status,
                    )
                )

    Review.objects.all().delete()
    Review.objects.bulk_create(new_reviews)

    refresh_reviews.enqueue(user, run_after=timezone.now() + timedelta(hours=REFRESH_INTERVAL_HOURS))


def sync_merge_packages_from_yaml(packages: set[str]) -> tuple[int, int]:
    """Sync MergeBugPackageInfo rows to match a set of package names.

    Removes packages not present in *packages* and creates missing ones with
    ``milestone_offset=0``.  Returns ``(added, removed)`` counts.
    """
    existing = set(MergeBugPackageInfo.objects.values_list("package", flat=True))

    to_add = packages - existing
    to_remove = existing - packages

    MergeBugPackageInfo.objects.filter(package__in=to_remove).delete()
    MergeBugPackageInfo.objects.bulk_create(
        [MergeBugPackageInfo(package=pkg, milestone_offset=0) for pkg in sorted(to_add)]
    )

    return len(to_add), len(to_remove)
