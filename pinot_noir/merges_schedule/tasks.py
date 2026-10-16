"""Background tasks that keep the merge schedule in sync with Launchpad."""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django_tasks import task
from django_tasks_db.models import DBTaskResult
from ubq.errors import RequestTimeoutError

from pinot_noir.data_manager.common import (
    get_devel_or_requested_release,
    get_launchpad_service_for_user,
    milestones_for_release,
)
from pinot_noir.data_manager.models import (
    BackportBugFilterSettings,
    BackportBugPackageInfo,
    MergeBugFilterSettings,
)
from pinot_noir.launchpad.models import LPUser
from pinot_noir.merges_schedule.models import Merge
from pinot_noir.merges_schedule.sync import MergeData, collect_bugs_for_type, merge_from_bug
from pinot_noir.pages.models import PageMetadata

SINGLE_MERGE_REFRESH_INTERVAL_HOURS = 12


def _backport_groups() -> list[tuple[str, set[str]]]:
    return [(info.name, set(info.packages)) for info in BackportBugPackageInfo.objects.all()]


def upsert_merge(data: MergeData) -> None:
    """Create or update the Merge row for *data*, resolving the assignee LPUser."""
    Merge.objects.update_or_create(
        lp_bug=data.lp_bug,
        defaults={
            "package": data.package,
            "merge_type": data.merge_type,
            "assignee": data.assignee,
            "assignee_user": (
                LPUser.objects.filter(username=data.assignee).first() if data.assignee else None
            ),
            "milestone": data.milestone,
            "status": data.status,
        },
    )


@task()
def refresh_merge_schedule(username: str, release_adjective: str | None = None) -> None:
    """Wipe the merge schedule, re-import bugs, then enqueue per-bug refreshes.

    Looks up the Ubuntu release by its adjective or uses devel by default, computes
    the six monthly milestones for that release cycle, then queries Launchpad for
    all bugs whose tags match ``MergeBugFilterSettings`` or
    ``BackportBugFilterSettings`` and whose milestone falls within that range.
    The ``Merge`` table is atomically replaced with the imported results.  Once
    the schedule is synced, staggered per-bug refresh tasks are enqueued for
    every imported bug.
    """
    release = get_devel_or_requested_release(release_adjective)

    valid_milestones = milestones_for_release(release.version)
    merge_settings = MergeBugFilterSettings.objects.filter(
        settings_type=MergeBugFilterSettings.TYPE_MERGE
    ).first()
    backport_settings = BackportBugFilterSettings.objects.first()

    service = get_launchpad_service_for_user(username)

    bugs_to_import: dict[str, tuple] = {}
    if merge_settings:
        collect_bugs_for_type(
            service, merge_settings.tags, valid_milestones, Merge.TYPE_MERGE, bugs_to_import
        )
    if backport_settings:
        collect_bugs_for_type(
            service,
            backport_settings.tags,
            valid_milestones,
            Merge.TYPE_BACKPORT,
            bugs_to_import,
        )

    # Fetch everything from Launchpad first so no network calls happen inside
    # the transaction below.
    backport_groups = _backport_groups()
    merges: list[MergeData] = []
    for bug_id, (_bug_record, milestone, merge_type) in bugs_to_import.items():
        try:
            full_bug = service.get_bug(bug_id, provider_name="launchpad")
        except RequestTimeoutError:
            continue
        if full_bug is None:
            continue
        merge = merge_from_bug(bug_id, full_bug, milestone, merge_type, backport_groups)
        if merge is not None:
            merges.append(merge)

    with transaction.atomic():
        for merge in merges:
            upsert_merge(merge)

        if merges:
            Merge.objects.exclude(lp_bug__in=[m.lp_bug for m in merges]).delete()

    PageMetadata.touch("merges-schedule")

    enqueue_all_merge_refreshes(username)


@task()
def refresh_single_merge(username: str, bug_id: int) -> None:
    """Refresh a single Merge record by its Launchpad bug ID.

    Fetches the latest bug data from Launchpad and updates (or creates) the
    corresponding ``Merge`` row.  If the bug cannot be fetched or parsed the
    existing record is left unchanged.
    """
    existing = Merge.objects.filter(lp_bug=bug_id).first()

    service = get_launchpad_service_for_user(username)

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

    merge = merge_from_bug(str(bug_id), full_bug, milestone, merge_type, _backport_groups())
    if merge is None:
        return

    upsert_merge(merge)


@task()
def queue_single_merge_refresh(username: str, bug_id: int) -> None:
    """Enqueue a refresh for *bug_id* and re-schedule it after the refresh interval.

    If the Merge no longer exists (e.g. it was invalidated), the cycle stops.
    """
    if not Merge.objects.filter(lp_bug=bug_id).exists():
        return
    refresh_single_merge.enqueue(username, bug_id)
    queue_single_merge_refresh.using(
        run_after=timezone.now() + timedelta(hours=SINGLE_MERGE_REFRESH_INTERVAL_HOURS),
    ).enqueue(username, bug_id)


def enqueue_all_merge_refreshes(username: str) -> None:
    """Enqueue staggered ``queue_single_merge_refresh`` tasks for every bug in the Merge table.

    Initial runs are spread evenly across ``SINGLE_MERGE_REFRESH_INTERVAL_HOURS`` so that
    subsequent periodic refreshes remain staggered rather than firing all at once.
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
        delay_hours = i * SINGLE_MERGE_REFRESH_INTERVAL_HOURS / count
        queue_single_merge_refresh.using(
            run_after=timezone.now() + timedelta(hours=delay_hours),
        ).enqueue(username, bug_id)
