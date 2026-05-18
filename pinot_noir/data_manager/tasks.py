"""Periodic data-refresh tasks for the data_manager application."""

from datetime import timedelta

from django.utils import timezone
from django_tasks import task
from ubq import QueryService

from pinot_noir.data_manager.helpers import (
    LP_STATUS_MAP,
    collect_bugs_for_type,
    merge_from_bug,
    milestones_for_release,
    package_from_url,
    release_from_branch,
)
from pinot_noir.data_manager.models import (
    BackportBugFilterSettings,
    LPReviewMarkerUser,
    MergeBugFilterSettings,
    MergeBugPackageInfo,
)
from pinot_noir.launchpad.models import LPUser, UbuntuRelease
from pinot_noir.merges_schedule.models import Merge
from pinot_noir.reviews.models import Review

REFRESH_INTERVAL_HOURS = 6


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

    valid_milestones = milestones_for_release(release.version)
    merge_settings = MergeBugFilterSettings.objects.filter(
        settings_type=MergeBugFilterSettings.TYPE_MERGE
    ).first()
    backport_settings = BackportBugFilterSettings.objects.first()

    service = QueryService()
    service.login(provider_name="launchpad")

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

    refresh_reviews.enqueue(run_after=timezone.now() + timedelta(hours=REFRESH_INTERVAL_HOURS))


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
