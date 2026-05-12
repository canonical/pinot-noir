from django.test import TestCase

from pinot_noir.launchpad.models import LPUser

from .models import Merge
from .views import sort_merges_default


class SortMergesDefaultTests(TestCase):
    def setUp(self):
        # Create some launchpad users for assignee_user
        self.alice = LPUser.objects.create(username="alice")
        self.bob = LPUser.objects.create(username="bob")
        self.carol = LPUser.objects.create(username="carol")
        self.dave = LPUser.objects.create(username="dave")

    def test_status_order(self):
        """Merges should sort by status in the order: new, started, projected, done."""
        Merge.objects.create(
            lp_bug=1, package="pkg1", status=Merge.STATUS_DONE, assignee_user=self.dave
        )
        Merge.objects.create(
            lp_bug=2, package="pkg2", status=Merge.STATUS_PROJECTED, assignee_user=self.carol
        )
        Merge.objects.create(
            lp_bug=3, package="pkg3", status=Merge.STATUS_STARTED, assignee_user=self.bob
        )
        Merge.objects.create(
            lp_bug=4, package="pkg4", status=Merge.STATUS_NEW, assignee_user=self.alice
        )

        merges = list(Merge.objects.select_related("assignee_user").all())
        sorted_merges = sort_merges_default(merges)

        self.assertEqual(
            [m.status for m in sorted_merges],
            [Merge.STATUS_NEW, Merge.STATUS_STARTED, Merge.STATUS_PROJECTED, Merge.STATUS_DONE],
        )

    def test_milestone_then_status_then_assignee(self):
        """Merges should sort by milestone first, then status (custom), then assignee username."""
        # Different milestones should sort first
        Merge.objects.create(
            lp_bug=10,
            package="pkg10",
            milestone="a",
            status=Merge.STATUS_NEW,
            assignee_user=self.bob,
        )
        Merge.objects.create(
            lp_bug=11,
            package="pkg11",
            milestone="b",
            status=Merge.STATUS_NEW,
            assignee_user=self.alice,
        )

        # Same milestone, different status to verify custom ordering
        Merge.objects.create(
            lp_bug=12,
            package="pkg12",
            milestone="c",
            status=Merge.STATUS_DONE,
            assignee_user=self.alice,
        )
        Merge.objects.create(
            lp_bug=13,
            package="pkg13",
            milestone="c",
            status=Merge.STATUS_STARTED,
            assignee_user=self.bob,
        )
        Merge.objects.create(
            lp_bug=14,
            package="pkg14",
            milestone="c",
            status=Merge.STATUS_NEW,
            assignee_user=self.carol,
        )

        merges = list(Merge.objects.select_related("assignee_user").all())
        sorted_merges = sort_merges_default(merges)

        # Verify the first two are milestone a then b
        self.assertEqual([m.milestone for m in sorted_merges[:2]], ["a", "b"])
        # Among milestone c items, status order should be new, started, done
        statuses_for_c = [m.status for m in sorted_merges if m.milestone == "c"]
        self.assertEqual(
            statuses_for_c, [Merge.STATUS_NEW, Merge.STATUS_STARTED, Merge.STATUS_DONE]
        )
