"""Periodic data-refresh tasks for the data_manager application."""

from datetime import timedelta

from django.utils import timezone
from django_tasks import task
from ubq import QueryService

from pinot_noir.data_manager.models import LPReviewMarkerUser
from pinot_noir.launchpad.models import LPUser
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
