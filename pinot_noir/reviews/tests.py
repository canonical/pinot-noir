from django.test import TestCase

from pinot_noir.launchpad.models import LPUser

from .models import Review
from .views import sort_reviews_default


class SortReviewsDefaultTests(TestCase):
    def setUp(self):
        self.alice = LPUser.objects.create(username="alice")
        self.bob = LPUser.objects.create(username="bob")

    def test_status_order(self):
        Review.objects.create(
            package="pkg1",
            mp_url="https://example.com/mp/1",
            status=Review.STATUS_APPROVED,
            reviewer_user=self.bob,
        )
        Review.objects.create(
            package="pkg2",
            mp_url="https://example.com/mp/2",
            status=Review.STATUS_NEEDS_REVIEW,
            reviewer_user=self.alice,
        )
        Review.objects.create(
            package="pkg3",
            mp_url="https://example.com/mp/3",
            status=Review.STATUS_WORK_IN_PROGRESS,
            reviewer_user=self.bob,
        )

        reviews = list(Review.objects.select_related("reviewer_user").all())
        sorted_reviews = sort_reviews_default(reviews)

        self.assertEqual(
            [r.status for r in sorted_reviews],
            [Review.STATUS_NEEDS_REVIEW, Review.STATUS_WORK_IN_PROGRESS, Review.STATUS_APPROVED],
        )


class ReviewsIndexTests(TestCase):
    def test_reviews_page_loads(self):
        response = self.client.get("/reviews")
        self.assertEqual(response.status_code, 200)
