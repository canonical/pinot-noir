"""Background tasks that keep the reviews page in sync with Launchpad."""

from django.db import transaction
from django.utils import timezone
from django_tasks import task
from django_tasks_db.models import DBTaskResult
from ubq.errors import RequestTimeoutError

from pinot_noir.data_manager.common import get_launchpad_service_for_user
from pinot_noir.launchpad.models import LPUser
from pinot_noir.pages.models import PageMetadata
from pinot_noir.reviews.models import Review
from pinot_noir.reviews.sync import ReviewData, review_from_merge_request


@task()
def refresh_reviews(username: str) -> None:
    """Replace the reviews table with current merge request data from Launchpad.

    Iterates over all stored LPUser records, queries Launchpad for each user's
    open merge proposals via ubq, then atomically replaces the contents of the
    reviews table.
    """

    DBTaskResult.objects.filter(
        task_path=refresh_reviews.module_path,
        status="READY",
        run_after__lte=timezone.now(),
    ).delete()

    service = get_launchpad_service_for_user(username)

    marker_usernames = set(
        LPUser.objects.filter(is_review_marker=True).values_list("username", flat=True)
    )
    reviewers_by_username = {
        user.username: user for user in LPUser.objects.filter(is_review_marker=False)
    }

    team_users = set(LPUser.objects.filter(is_team_member=True))
    team_usernames = set(user.username for user in team_users)

    # Collect reviews from Launchpad.
    reviews_to_import: dict[str, tuple[ReviewData, LPUser]] = {}

    for lp_user in team_users:
        try:
            merge_requests = service.get_merge_requests_from_user(
                user_id=lp_user.username,
                provider_name="launchpad",
            )
        except RequestTimeoutError:
            continue
        for mr in merge_requests:
            review = review_from_merge_request(
                mr,
                submitter=lp_user.username,
                team_usernames=team_usernames,
                marker_usernames=marker_usernames,
                reviewer_usernames=set(reviewers_by_username),
            )
            if review is not None:
                reviews_to_import[review.mp_url] = (review, lp_user)

    # Atomically update the Review table.
    with transaction.atomic():
        for mp_url, (review, submitter_user) in reviews_to_import.items():
            Review.objects.update_or_create(
                mp_url=mp_url,
                defaults={
                    "package": review.package,
                    "release_version": review.release_version,
                    "source_branch": review.source_branch,
                    "lines_added": review.lines_added,
                    "lines_removed": review.lines_removed,
                    "reviewer": review.reviewer,
                    "reviewer_user": reviewers_by_username.get(review.reviewer),
                    "submitter": review.submitter,
                    "submitter_user": submitter_user,
                    "status": review.status,
                },
            )

        if reviews_to_import:
            Review.objects.exclude(mp_url__in=reviews_to_import.keys()).delete()

    PageMetadata.touch("reviews")
