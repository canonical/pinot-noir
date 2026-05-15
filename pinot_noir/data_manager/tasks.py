"""Periodic data-refresh tasks for the data_manager application."""

from datetime import timedelta

from django.utils import timezone
from django_tasks import task
from ubq import QueryService
from ubq.models import BugRecord, BugSearchRecord

from pinot_noir.data_manager.models import (
    BackportBugFilterSettings,
    BackportBugPackageInfo,
    LPReviewMarkerUser,
    MergeBugFilterSettings,
)
from pinot_noir.launchpad.models import LPUser, UbuntuRelease
from pinot_noir.merges_schedule.models import Merge
from pinot_noir.reviews.models import Review

REFRESH_INTERVAL_HOURS = 6

# Map Launchpad queue_status values to Review status choices.
_LP_STATUS_MAP: dict[str, str] = {
    "Work in progress": Review.STATUS_WORK_IN_PROGRESS,
    "Needs review": Review.STATUS_NEEDS_REVIEW,
    "Approved": Review.STATUS_APPROVED,
    "Rejected": Review.STATUS_NEEDS_FIXING,
    "Code failed to merge": Review.STATUS_NEEDS_FIXING,
    "Queued": Review.STATUS_UNDER_REVIEW,
    "Merged": Review.STATUS_APPROVED,
    "Superseded": Review.STATUS_NEEDS_FIXING,
}


def _package_from_url(web_url: str) -> str:
    """Extract the source package name from a Launchpad merge proposal URL.

    Expected URL form:
    ``https://code.launchpad.net/~.../ubuntu/+source/<PACKAGE>/...``
    """
    try:
        return web_url.split("/+source/", 1)[1].split("/", maxsplit=1)[0]
    except IndexError:
        return ""


def _release_from_branch(branch: str | None) -> str:
    """Extract the Ubuntu release series from a git branch path.

    Branch paths are typically ``refs/heads/ubuntu/<SERIES>`` or
    ``refs/heads/ubuntu/<SERIES>-proposed``.
    """
    if not branch:
        return ""
    parts = branch.split("/")
    for i, part in enumerate(parts):
        if part == "ubuntu" and i + 1 < len(parts):
            return parts[i + 1].split("-")[0]
    return ""


def _milestones_for_release(version: str) -> set[str]:
    """Return the set of valid LP milestone names for a Ubuntu release cycle.

    Given a version like ``'26.04'``, returns the six monthly milestones
    spanning the cycle: ``{'25.11', '25.12', '26.01', '26.02', '26.03', '26.04'}``.
    """
    year_str, month_str = version.split(".")
    year = int(year_str)
    month = int(month_str)

    milestones: set[str] = set()
    for i in range(6):
        m = month - i
        y = year
        while m <= 0:
            m += 12
            y -= 1
        milestones.add(f"{y:02d}.{m:02d}")
    return milestones


def _backport_package_name(packages: list[str]) -> str:
    """Return the BackportBugPackageInfo group name matching the bug's packages.

    Falls back to the first package name if no matching group is found.
    """
    package_set = set(packages)
    for info in BackportBugPackageInfo.objects.all():
        if set(info.packages) <= package_set:
            return info.name
    return packages[0]


# Map Launchpad bug task status values to Merge status choices.
_LP_BUG_STATUS_MAP: dict[str, str] = {
    "New": Merge.STATUS_NEW,
    "Incomplete": Merge.STATUS_NEW,
    "Confirmed": Merge.STATUS_NEW,
    "Triaged": Merge.STATUS_NEW,
    "In Progress": Merge.STATUS_STARTED,
    "Fix Committed": Merge.STATUS_STARTED,
    "Fix Released": Merge.STATUS_DONE,
}


def _collect_bugs_for_type(
    service: QueryService,
    filter_settings: MergeBugFilterSettings,
    valid_milestones: set[str],
    merge_type: str,
    bugs: dict[str, tuple],
) -> None:
    """Search LP for bugs matching filter_settings across all valid milestones."""
    if not filter_settings.tags:
        return
    for raw_milestone in valid_milestones:
        lp_milestone = f"ubuntu-{raw_milestone}"
        for status in (None, "Fix Released"):
            for bug in service.search_bugs(
                BugSearchRecord(
                    provider_name="launchpad",
                    tags=filter_settings.tags,
                    milestone=lp_milestone,
                    status=status,
                ),
                provider_name="launchpad",
            ):
                bugs.setdefault(bug.id, (bug, raw_milestone, merge_type))


def _merge_from_bug(
    bug_id: str,
    full_bug: BugRecord,
    milestone: str,
    merge_type: str,
) -> Merge | None:
    """Build a Merge instance from a full bug record, or None if it should be skipped."""
    if not full_bug.bug_tasks:
        return None

    if merge_type == Merge.TYPE_BACKPORT:
        packages = [p for bug_task in full_bug.bug_tasks if (p := bug_task.package_name or "")]
        if not packages:
            return None
        package = _backport_package_name(packages)
    else:
        package = full_bug.bug_tasks[0].package_name or ""
        if not package:
            return None

    first_task = full_bug.bug_tasks[0]
    assignee_username = ""
    assignee_user = None
    status = Merge.STATUS_NEW
    if first_task.assignee and first_task.assignee.username:
        assignee_username = first_task.assignee.username
        assignee_user = LPUser.objects.filter(username=assignee_username).first()
    if first_task.status:
        status = _LP_BUG_STATUS_MAP.get(first_task.status, Merge.STATUS_NEW)

    try:
        bug_number = int(bug_id)
    except ValueError:
        return None

    return Merge(
        lp_bug=bug_number,
        package=package,
        merge_type=merge_type,
        assignee=assignee_username,
        assignee_user=assignee_user,
        milestone=milestone,
        status=status,
    )


@task()
def refresh_merge_schedule(release_adjective: str) -> None:
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

    valid_milestones = _milestones_for_release(release.version)
    merge_settings = MergeBugFilterSettings.objects.filter(
        settings_type=MergeBugFilterSettings.TYPE_MERGE
    ).first()
    backport_settings = BackportBugFilterSettings.objects.first()

    service = QueryService()
    service.login(provider_name="launchpad")

    bugs_to_import: dict[str, tuple] = {}
    if merge_settings:
        _collect_bugs_for_type(
            service, merge_settings, valid_milestones, Merge.TYPE_MERGE, bugs_to_import
        )
    if backport_settings:
        _collect_bugs_for_type(
            service, backport_settings, valid_milestones, Merge.TYPE_BACKPORT, bugs_to_import
        )

    new_merges: list[Merge] = []
    for bug_id, (bug_record, milestone, merge_type) in bugs_to_import.items():
        full_bug = service.get_bug(bug_id, provider_name="launchpad")
        if full_bug is None:
            continue
        merge = _merge_from_bug(bug_id, full_bug, milestone, merge_type)
        if merge is not None:
            new_merges.append(merge)

    Merge.objects.all().delete()
    Merge.objects.bulk_create(new_merges)


@task()
def refresh_reviews() -> None:
    """Replace the reviews table with current merge request data from Launchpad.

    Iterates over all stored LPUser records, queries Launchpad for each user's
    open merge proposals via ubq, then atomically replaces the contents of the
    reviews table.  After completion the task re-enqueues itself to run again
    after ``REFRESH_INTERVAL_HOURS`` hours.
    """

    service = QueryService()
    service.login(provider_name="launchpad")

    marker_usernames = set(LPReviewMarkerUser.objects.values_list("username", flat=True))

    new_reviews: list[Review] = []
    for lp_user in LPUser.objects.all():
        merge_requests = service.get_merge_requests_from_user(
            user_id=lp_user.username,
            provider_name="launchpad",
        )
        for mr in merge_requests:
            package = _package_from_url(mr.web_url or "")
            release_version = _release_from_branch(mr.target_branch)
            status = _LP_STATUS_MAP.get(mr.status or "", Review.STATUS_NEEDS_REVIEW)

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

    refresh_reviews.enqueue(run_after=timezone.now() + timedelta(hours=REFRESH_INTERVAL_HOURS))
