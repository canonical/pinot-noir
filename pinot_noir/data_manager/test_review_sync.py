from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import TestCase

from pinot_noir.data_manager.helpers import review_status_from_merge_request
from pinot_noir.data_manager.tasks import refresh_reviews
from pinot_noir.launchpad.models import LPUser
from pinot_noir.reviews.models import Review


def _mr(web_url, status, **kwargs):
    """Build a minimal merge-request namespace."""
    kwargs.setdefault("votes", [])
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
        submitter = LPUser.objects.create(username="graysonwolf", is_team_member=True)
        LPUser.objects.create(username="ubuntu-server", is_review_marker=True)

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


def _vote(username, vote, voted_at=None):
    """Build a minimal merge-request vote namespace."""
    return SimpleNamespace(
        voter=SimpleNamespace(username=username), vote=vote, voted_at=voted_at
    )


class ReviewStatusFromMergeRequestTests(TestCase):
    def test_non_needs_review_status_ignores_votes(self):
        mr = _mr("https://lp.test/merge/1", "Approved", votes=[_vote("alice", "Needs Fixing")])
        self.assertEqual(
            review_status_from_merge_request(mr, set()),
            Review.STATUS_APPROVED,
        )

    def test_needs_fixing_vote_takes_precedence(self):
        mr = _mr(
            "https://lp.test/merge/1",
            "Needs review",
            votes=[_vote("teammate", "Approve"), _vote("alice", "Needs Fixing")],
        )
        self.assertEqual(
            review_status_from_merge_request(mr, {"teammate"}),
            Review.STATUS_NEEDS_FIXING,
        )

    def test_needs_information_vote(self):
        mr = _mr(
            "https://lp.test/merge/1",
            "Needs review",
            votes=[_vote("alice", "Needs Information")],
        )
        self.assertEqual(
            review_status_from_merge_request(mr, set()),
            Review.STATUS_NEEDS_INFORMATION,
        )

    def test_team_member_approval(self):
        mr = _mr(
            "https://lp.test/merge/1",
            "Needs review",
            votes=[_vote("teammate", "Approve")],
        )
        self.assertEqual(
            review_status_from_merge_request(mr, {"teammate"}),
            Review.STATUS_TEAM_APPROVED,
        )

    def test_community_member_approval(self):
        mr = _mr(
            "https://lp.test/merge/1",
            "Needs review",
            votes=[_vote("outsider", "Approve")],
        )
        self.assertEqual(
            review_status_from_merge_request(mr, {"teammate"}),
            Review.STATUS_COMMUNITY_APPROVED,
        )

    def test_team_approval_preferred_over_community(self):
        mr = _mr(
            "https://lp.test/merge/1",
            "Needs review",
            votes=[_vote("outsider", "Approve"), _vote("teammate", "Approve")],
        )
        self.assertEqual(
            review_status_from_merge_request(mr, {"teammate"}),
            Review.STATUS_TEAM_APPROVED,
        )

    def test_no_relevant_votes_stays_needs_review(self):
        mr = _mr(
            "https://lp.test/merge/1",
            "Needs review",
            votes=[_vote("alice", "Abstain")],
        )
        self.assertEqual(
            review_status_from_merge_request(mr, set()),
            Review.STATUS_NEEDS_REVIEW,
        )

    def test_only_latest_vote_per_voter_considered(self):
        mr = _mr(
            "https://lp.test/merge/1",
            "Needs review",
            votes=[
                _vote("alice", "Needs Fixing", voted_at=datetime(2026, 1, 1)),
                _vote("alice", "Approve", voted_at=datetime(2026, 1, 2)),
            ],
        )
        self.assertEqual(
            review_status_from_merge_request(mr, set()),
            Review.STATUS_COMMUNITY_APPROVED,
        )
