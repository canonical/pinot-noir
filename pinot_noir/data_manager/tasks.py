"""Periodic data-refresh tasks for the data_manager application."""

import logging
from datetime import timedelta
from typing import Any

from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone
from django_tasks import task
from django_tasks_db.models import DBTaskResult
from ubq import QueryService
from ubq.errors import RequestTimeoutError
from ubq.models import BugSubmissionRecord, ProviderCredentials, UserRecord

from pinot_noir.data_manager.helpers import (
    LP_REVIEW_SKIP_STATUSES,
    LP_STATUS_MAP,
    collect_bugs_for_type,
    merge_from_bug,
    milestones_for_release,
    package_from_url,
    prepare_backport_bugs_for_all_packages,
    prepare_merge_bugs_for_all_packages,
    release_from_branch,
)
from pinot_noir.data_manager.models import (
    BackportBugFilterSettings,
    BackportBugPackageInfo,
    LPReviewMarkerUser,
    MergeBugFilterSettings,
    MergeBugPackageInfo,
    UserTokens,
)
from pinot_noir.launchpad.models import LPUser, UbuntuRelease
from pinot_noir.merges_schedule.models import Merge
from pinot_noir.reviews.models import Review

REFRESH_INTERVAL_HOURS = 6
SINGLE_MERGE_REFRESH_INTERVAL_HOURS = 12
PRUNE_INTERVAL_HOURS = 24
PRUNE_AGE_DAYS = 7
STUCK_RUNNING_HOURS = 24


def _get_devel_release() -> UbuntuRelease:
    release = UbuntuRelease.objects.filter(status=UbuntuRelease.STATUS_DEVEL).first()
    if release is None:
        raise ObjectDoesNotExist("No Ubuntu development release found.")
    return release


def _get_launchpad_service_for_user(username: str) -> QueryService:
    user = User.objects.get(username=username)
    tokens = UserTokens.objects.filter(user=user).first()
    if tokens is None or not tokens.lp_token:
        raise ObjectDoesNotExist(f"No Launchpad token configured for user '{username}'.")

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
    username: str,
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

    service = _get_launchpad_service_for_user(username)
    return prepare_merge_bugs_for_all_packages(service, ubuntu_release, filter_settings)


def submit_prepared_merge_bug_submissions(
    username: str,
    submissions: list[tuple[str, BugSubmissionRecord]],
) -> tuple[int, int]:
    """Submit prepared merge bug submissions and mark package rows as filed.

    Returns ``(submitted_count, failed_count)``.
    """
    service = _get_launchpad_service_for_user(username)

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


def prepare_backport_bug_submissions(
    username: str,
    release_adjective: str | None = None,
) -> list[tuple[str, BugSubmissionRecord]]:
    """Prepare backport bug submissions for all packages."""
    if release_adjective:
        ubuntu_release = UbuntuRelease.objects.get(adjective=release_adjective)
    else:
        ubuntu_release = _get_devel_release()

    filter_settings = BackportBugFilterSettings.objects.first()
    if filter_settings is None:
        raise ObjectDoesNotExist("No backport bug filter settings found.")

    return prepare_backport_bugs_for_all_packages(ubuntu_release, filter_settings)


def submit_prepared_backport_bug_submissions(
    username: str,
    submissions: list[tuple[str, BugSubmissionRecord]],
) -> tuple[int, int]:
    """Submit prepared backport bug submissions and mark package rows as filed.

    Returns ``(submitted_count, failed_count)``.
    """
    service = _get_launchpad_service_for_user(username)

    submitted_count = 0
    failed_count = 0
    for package_name, submission in submissions:
        bug = service.submit_bug(submission=submission, provider_name="launchpad")
        if bug is None:
            failed_count += 1
            continue

        BackportBugPackageInfo.objects.filter(name=package_name).update(bug_filed_this_cycle=True)
        submitted_count += 1

    return submitted_count, failed_count


@task()
def refresh_merge_schedule(username: str, release_adjective: str) -> None:
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

    service = _get_launchpad_service_for_user(username)

    bugs_to_import: dict[str, tuple] = {}
    if merge_settings:
        collect_bugs_for_type(
            service, merge_settings, valid_milestones, Merge.TYPE_MERGE, bugs_to_import
        )
    if backport_settings:
        collect_bugs_for_type(
            service, backport_settings, valid_milestones, Merge.TYPE_BACKPORT, bugs_to_import
        )

    for bug_id, (bug_record, milestone, merge_type) in bugs_to_import.items():
        try:
            full_bug = service.get_bug(bug_id, provider_name="launchpad")
        except RequestTimeoutError:
            continue
        if full_bug is None:
            continue
        merge = merge_from_bug(bug_id, full_bug, milestone, merge_type)
        if merge is None:
            continue
        Merge.objects.update_or_create(
            lp_bug=merge.lp_bug,
            defaults={
                "package": merge.package,
                "merge_type": merge.merge_type,
                "assignee": merge.assignee,
                "assignee_user": merge.assignee_user,
                "milestone": merge.milestone,
                "status": merge.status,
            },
        )


@task()
def refresh_reviews(username: str) -> None:
    """Replace the reviews table with current merge request data from Launchpad.

    Iterates over all stored LPUser records, queries Launchpad for each user's
    open merge proposals via ubq, then atomically replaces the contents of the
    reviews table.  After completion the task re-enqueues itself to run again
    after ``REFRESH_INTERVAL_HOURS`` hours.
    """

    DBTaskResult.objects.filter(
        task_path=refresh_reviews.module_path,
        status="READY",
    ).delete()

    service = _get_launchpad_service_for_user(username)

    marker_usernames = set(LPReviewMarkerUser.objects.values_list("username", flat=True))

    for lp_user in LPUser.objects.all():
        try:
            merge_requests = service.get_merge_requests_from_user(
                user_id=lp_user.username,
                provider_name="launchpad",
            )
        except RequestTimeoutError:
            continue
        for mr in merge_requests:
            if mr.status in LP_REVIEW_SKIP_STATUSES:
                continue

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

                Review.objects.update_or_create(
                    mp_url=mr.web_url or "",
                    defaults={
                        "package": package,
                        "release_version": release_version,
                        "source_branch": mr.source_branch or "",
                        "lines_added": mr.added_lines,
                        "lines_removed": mr.removed_lines,
                        "reviewer": reviewer_username,
                        "reviewer_user": reviewer_user,
                        "submitter": lp_user.username,
                        "submitter_user": lp_user,
                        "status": status,
                    },
                )

    refresh_reviews.using(
        run_after=timezone.now() + timedelta(hours=REFRESH_INTERVAL_HOURS)
    ).enqueue(username)


@task()
def refresh_single_merge(username: str, bug_id: int) -> None:
    """Refresh a single Merge record by its Launchpad bug ID.

    Fetches the latest bug data from Launchpad and updates (or creates) the
    corresponding ``Merge`` row.  If the bug cannot be fetched or parsed the
    existing record is left unchanged.
    """
    existing = Merge.objects.filter(lp_bug=bug_id).first()

    service = _get_launchpad_service_for_user(username)

    try:
        full_bug = service.get_bug(str(bug_id), provider_name="launchpad")
    except RequestTimeoutError:
        return
    if full_bug is None:
        return

    if full_bug.bug_tasks and full_bug.bug_tasks[0].status == "Invalid":
        Merge.objects.filter(lp_bug=bug_id).delete()
        return


    merge_type = existing.merge_type if existing else Merge.TYPE_MERGE
    milestone = existing.milestone if existing else ""

    merge = merge_from_bug(str(bug_id), full_bug, milestone, merge_type)
    if merge is None:
        return

    Merge.objects.update_or_create(
        lp_bug=bug_id,
        defaults={
            "package": merge.package,
            "merge_type": merge.merge_type,
            "assignee": merge.assignee,
            "assignee_user": merge.assignee_user,
            "milestone": merge.milestone,
            "status": merge.status,
        },
    )


@task()
def queue_single_merge_refresh(
    username: str,
    bug_id: int,
    interval_hours: int = SINGLE_MERGE_REFRESH_INTERVAL_HOURS,
) -> None:
    """Enqueue a refresh for *bug_id* and re-schedule this task after *interval_hours* hours.

    If the Merge no longer exists (e.g. it was invalidated), the cycle stops.
    """
    if not Merge.objects.filter(lp_bug=bug_id).exists():
        return
    refresh_single_merge.enqueue(username, bug_id)
    queue_single_merge_refresh.using(
        run_after=timezone.now() + timedelta(hours=interval_hours),
    ).enqueue(username, bug_id, interval_hours)


@task()
def enqueue_all_merge_refreshes(
    username: str,
    single_merge_refresh_interval_hours: int = SINGLE_MERGE_REFRESH_INTERVAL_HOURS,
) -> None:
    """Enqueue staggered ``queue_single_merge_refresh`` tasks for every bug in the Merge table.

    Initial runs are spread evenly across *single_merge_refresh_interval_hours* so that subsequent
    periodic refreshes remain staggered rather than firing all at once.
    """
    # Clear existing queued single-merge refreshes to avoid duplicates
    DBTaskResult.objects.filter(
        task_path__in=[
            queue_single_merge_refresh.module_path,
            refresh_single_merge.module_path,
        ],
        status="READY",
    ).delete()

    bug_ids = list(
        Merge.objects.exclude(status=Merge.STATUS_DONE).values_list("lp_bug", flat=True)
    )
    count = len(bug_ids)
    if not count:
        return

    for i, bug_id in enumerate(bug_ids):
        delay_hours = i * single_merge_refresh_interval_hours / count
        queue_single_merge_refresh.using(
            run_after=timezone.now() + timedelta(hours=delay_hours),
        ).enqueue(username, bug_id, single_merge_refresh_interval_hours)


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


@task()
def prune_task_results() -> None:
    """Delete old completed/failed task results and reset stuck running tasks.

    Removes ``SUCCESSFUL`` and ``FAILED`` ``DBTaskResult`` rows older than
    ``PRUNE_AGE_DAYS`` days.  Tasks stuck in ``RUNNING`` status for longer than
    ``STUCK_RUNNING_HOURS`` hours are reset to ``FAILED``.

    Re-enqueues itself to run again after ``PRUNE_INTERVAL_HOURS`` hours.
    """
    # Prevent duplicate scheduled prune tasks
    DBTaskResult.objects.filter(
        task_path=prune_task_results.module_path,
        status="READY",
    ).delete()

    cutoff = timezone.now() - timedelta(days=PRUNE_AGE_DAYS)
    deleted_count, _ = DBTaskResult.objects.filter(
        status__in=["SUCCESSFUL", "FAILED"],
        finished_at__lt=cutoff,
    ).delete()

    stuck_cutoff = timezone.now() - timedelta(hours=STUCK_RUNNING_HOURS)
    stuck_count = DBTaskResult.objects.filter(
        status="RUNNING",
        started_at__lt=stuck_cutoff,
    ).update(status="FAILED")

    if deleted_count or stuck_count:
        logger = logging.getLogger("django_tasks_db")
        logger.info(
            "Pruned %d old task results, reset %d stuck tasks.",
            deleted_count,
            stuck_count,
        )

    prune_task_results.using(
        run_after=timezone.now() + timedelta(hours=PRUNE_INTERVAL_HOURS),
    ).enqueue()
