"""Shared data_manager tasks: bug filing, task pruning and weekly scheduling.

Page-specific sync tasks live with their apps (merges_schedule.tasks,
reviews.tasks).
"""

import logging
from datetime import timedelta

from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone
from django_tasks import task
from django_tasks_db.models import DBTaskResult
from ubq.models import BugSubmissionRecord

from pinot_noir.data_manager.bug_filing import (
    prepare_backport_bugs_for_all_packages,
    prepare_merge_bugs_for_all_packages,
)
from pinot_noir.data_manager.common import (
    get_devel_or_requested_release,
    get_launchpad_service_for_user,
)
from pinot_noir.data_manager.models import (
    BackportBugFilterSettings,
    BackportBugPackageInfo,
    MergeBugFilterSettings,
    MergeBugPackageInfo,
    WeeklyTask,
)

# Re-exported so task rows already queued under the old
# ``pinot_noir.data_manager.tasks.<name>`` paths still resolve.
from pinot_noir.merges_schedule.tasks import (  # noqa: F401
    enqueue_all_merge_refreshes,
    queue_single_merge_refresh,
    refresh_merge_schedule,
    refresh_single_merge,
)
from pinot_noir.pages.registry import get_pages
from pinot_noir.reviews.tasks import refresh_reviews  # noqa: F401

PRUNE_AGE_DAYS = 7
STUCK_RUNNING_HOURS = 24
WEEKLY_SCHEDULER_INTERVAL_MINUTES = 15


def prepare_merge_bug_submissions(
    username: str,
    release_adjective: str | None = None,
) -> list[tuple[str, BugSubmissionRecord]]:
    """Prepare merge bug submissions for all packages using a user's LP token."""
    ubuntu_release = get_devel_or_requested_release(release_adjective)

    filter_settings = MergeBugFilterSettings.objects.filter(
        settings_type=MergeBugFilterSettings.TYPE_MERGE
    ).first()
    if filter_settings is None:
        raise ObjectDoesNotExist("No merge bug filter settings found.")

    service = get_launchpad_service_for_user(username)
    return prepare_merge_bugs_for_all_packages(service, ubuntu_release, filter_settings)


def submit_prepared_merge_bug_submissions(
    username: str,
    submissions: list[tuple[str, BugSubmissionRecord]],
) -> tuple[int, int]:
    """Submit prepared merge bug submissions and mark package rows as filed.

    Returns ``(submitted_count, failed_count)``.
    """
    service = get_launchpad_service_for_user(username)

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
    ubuntu_release = get_devel_or_requested_release(release_adjective)

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
    service = get_launchpad_service_for_user(username)

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
def submit_merge_bugs(username: str, release_adjective: str | None = None) -> None:
    """Prepare and submit all needed merge bug submissions for a release."""
    submissions = prepare_merge_bug_submissions(username, release_adjective)
    if submissions:
        submit_prepared_merge_bug_submissions(username, submissions)


@task()
def submit_backport_bugs(username: str, release_adjective: str | None = None) -> None:
    """Prepare and submit all needed backport bug submissions for a release."""
    submissions = prepare_backport_bug_submissions(username, release_adjective)
    if submissions:
        submit_prepared_backport_bug_submissions(username, submissions)


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
def prune_task_results(username: str | None = None) -> None:
    """Delete old completed/failed task results and reset stuck running tasks.

    Username field is currently ignored.
    """
    # Prevent duplicate scheduled prune tasks
    DBTaskResult.objects.filter(
        task_path=prune_task_results.module_path,
        status="READY",
        run_after__lte=timezone.now(),
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


def get_schedulable_tasks() -> dict:
    """Return a mapping of WeeklyTask task keys to their task callables.

    Page refresh tasks come from the page registry; the rest are listed here.
    """
    schedulable = [task for page in get_pages() if (task := page.get_refresh_task()) is not None]
    schedulable += [prune_task_results, submit_merge_bugs, submit_backport_bugs]
    return {t.name: t for t in schedulable}


@task()
def schedule_weekly_tasks() -> None:
    """Enqueue each due WeeklyTask entry and re-schedule self."""
    DBTaskResult.objects.filter(
        task_path=schedule_weekly_tasks.module_path,
        status="READY",
    ).delete()

    now = timezone.now()
    logger = logging.getLogger(__name__)
    try:
        schedulable = get_schedulable_tasks()

        for weekly_task in WeeklyTask.objects.filter(enabled=True):
            # Still enqueued for a future run; leave it alone.
            if weekly_task.next_run is not None and weekly_task.next_run > now:
                continue

            underlying_task = schedulable.get(weekly_task.task)
            if underlying_task is None:
                continue

            run_at = weekly_task.next_occurrence(now)
            if run_at is None:
                continue

            kwargs = {}
            if weekly_task.user is not None:
                kwargs["username"] = weekly_task.user.username

            try:
                underlying_task.using(run_after=run_at).enqueue(**kwargs)
            except Exception:
                logger.exception("Failed to enqueue weekly task id=%s", weekly_task.pk)
                continue

            weekly_task.next_run = run_at
            weekly_task.save(update_fields=["next_run"])
    finally:
        # Always keep the scheduler chain alive, even if processing above failed.
        schedule_weekly_tasks.using(
            run_after=now + timedelta(minutes=WEEKLY_SCHEDULER_INTERVAL_MINUTES),
        ).enqueue()
