from django.shortcuts import render

from .models import Review


STATUS_ORDER = {
    Review.STATUS_NEEDS_REVIEW: 0,
    Review.STATUS_WORK_IN_PROGRESS: 1,
    Review.STATUS_UNDER_REVIEW: 2,
    Review.STATUS_APPROVED: 3,
    Review.STATUS_NEEDS_FIXING: 4,
    Review.STATUS_NEEDS_INFORMATION: 5,
}


def sort_reviews_default(reviews):
    """Sort reviews by status, submitter, package, version, then reviewer username."""
    return sorted(
        reviews,
        key=lambda r: (
            STATUS_ORDER.get(r.status, -1),
            r.submitter_user.username if r.submitter_user else r.submitter,
            r.package,
            r.release_version or "",
            r.reviewer_user.username if r.reviewer_user else r.reviewer,
        ),
    )


def index(request):
    """Render the reviews schedule page using stored Review objects."""
    reviews = Review.objects.select_related("reviewer_user", "submitter_user").all()
    sorted_reviews = sort_reviews_default(reviews)

    releases = sorted({r.release_version for r in reviews if r.release_version})
    reviewers = sorted({(r.reviewer_user.username if r.reviewer_user else (r.reviewer or "UNASSIGNED")) for r in reviews})
    submitters = sorted({(r.submitter_user.username if r.submitter_user else (r.submitter or "UNASSIGNED")) for r in reviews})
    statuses = [s for s, _ in sorted(Review.STATUS_CHOICES, key=lambda item: STATUS_ORDER.get(item[0], -1))]

    context = {
        "title": "Reviews",
        "reviews": sorted_reviews,
        "releases": releases,
        "reviewers": reviewers,
        "submitters": submitters,
        "statuses": statuses,
    }

    return render(request, "reviews/index.html", context)
