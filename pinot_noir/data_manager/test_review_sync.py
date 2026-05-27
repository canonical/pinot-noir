from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import TestCase

from pinot_noir.data_manager.models import LPReviewMarkerUser
from pinot_noir.data_manager.tasks import refresh_reviews
from pinot_noir.launchpad.models import LPUser
from pinot_noir.reviews.models import Review


def _mr(web_url, status, **kwargs):
    """Build a minimal merge-request namespace."""
    return SimpleNamespace(
        web_url=web_url,
        target_branch="refs/heads/ubuntu/resolute",
        status=status,
        assignees=[SimpleNamespace(username="ubuntu-server")],
        source_branch="refs/heads/topic/branch",
        added_lines=10,
        removed_lines=2,
        **kwargs,
    )


class RefreshReviewsTests(TestCase):
    @patch("pinot_noir.data_manager.tasks._get_launchpad_service_for_user")
    def test_skips_rejected_and_superseded_merge_proposals(self, get_service_mock):
        submitter = LPUser.objects.create(username="graysonwolf")
        LPUser.objects.create(username="ubuntu-server")
        LPReviewMarkerUser.objects.create(username="ubuntu-server")

        service = MagicMock()
        service.get_merge_requests_from_user.side_effect = lambda user_id, **kw: [
            _mr("https://lp.test/merge/1", "Rejected"),
            _mr("https://lp.test/merge/2", "Superseded"),
            _mr("https://lp.test/merge/3", "Needs review"),
        ] if user_id == "graysonwolf" else []
        get_service_mock.return_value = service

        refresh_reviews.call("alice")

        self.assertEqual(Review.objects.count(), 1)
        review = Review.objects.get()
        self.assertEqual(review.mp_url, "https://lp.test/merge/3")
        self.assertEqual(review.submitter_user, submitter)
        self.assertEqual(review.status, Review.STATUS_NEEDS_REVIEW)
