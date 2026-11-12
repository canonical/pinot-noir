from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class TeamUserMigrationTests(TransactionTestCase):
    """Exercise the split with shared roles, existing users, and report links."""

    old_targets = [
        ("launchpad", "0005_lpuser_is_team_member_lpuser_is_review_marker"),
        ("merges_schedule", "0004_alter_merge_status"),
        ("reviews", "0003_alter_review_status"),
    ]

    def setUp(self):
        executor = MigrationExecutor(connection)
        self.latest_targets = executor.loader.graph.leaf_nodes()
        executor.migrate(self.old_targets)
        apps = executor.loader.project_state(self.old_targets).apps
        User = apps.get_model("auth", "User")
        LPUser = apps.get_model("launchpad", "LPUser")
        Merge = apps.get_model("merges_schedule", "Merge")
        Review = apps.get_model("reviews", "Review")

        self.existing = User.objects.create(
            username="existing", email="keep@example.com", password="!", is_active=False
        )
        shared = LPUser.objects.create(
            username="existing",
            email_md5="not-an-email",
            is_team_member=True,
            is_review_marker=True,
        )
        member = LPUser.objects.create(username="member", is_team_member=True)
        LPUser.objects.create(username="marker", is_review_marker=True)
        outsider = LPUser.objects.create(username="outsider")
        Merge.objects.create(
            lp_bug=1, package="pkg", assignee=shared.username, assignee_user=shared
        )
        Merge.objects.create(
            lp_bug=2, package="pkg", assignee=outsider.username, assignee_user=outsider
        )
        Review.objects.create(
            package="pkg",
            mp_url="https://example.test/review",
            reviewer=shared.username,
            reviewer_user=shared,
            submitter=member.username,
            submitter_user=member,
        )

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.latest_targets)

    def test_split_moves_roles_and_links_and_reverses(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.latest_targets)
        apps = executor.loader.project_state(self.latest_targets).apps
        User = apps.get_model("auth", "User")
        ReviewMarker = apps.get_model("launchpad", "ReviewMarker")
        Merge = apps.get_model("merges_schedule", "Merge")
        Review = apps.get_model("reviews", "Review")

        self.assertEqual(
            set(ReviewMarker.objects.values_list("username", flat=True)),
            {"existing", "marker"},
        )
        existing = User.objects.get(username="existing")
        member = User.objects.get(username="member")
        self.assertTrue(existing.is_active)
        self.assertEqual(existing.email, "keep@example.com")
        self.assertTrue(member.password.startswith("!"))
        self.assertEqual(Merge.objects.get(lp_bug=1).assignee_user_id, existing.pk)
        self.assertIsNone(Merge.objects.get(lp_bug=2).assignee_user_id)
        self.assertEqual(Merge.objects.get(lp_bug=2).assignee, "outsider")
        review = Review.objects.get()
        self.assertEqual(review.reviewer_user_id, existing.pk)
        self.assertEqual(review.submitter_user_id, member.pk)

        executor = MigrationExecutor(connection)
        executor.migrate(self.old_targets)
        old_apps = executor.loader.project_state(self.old_targets).apps
        LPUser = old_apps.get_model("launchpad", "LPUser")
        Merge = old_apps.get_model("merges_schedule", "Merge")
        Review = old_apps.get_model("reviews", "Review")
        restored = LPUser.objects.get(username="existing")
        self.assertTrue(restored.is_team_member)
        self.assertTrue(restored.is_review_marker)
        self.assertEqual(Merge.objects.get(lp_bug=2).assignee_user_id, "outsider")
        restored_review = Review.objects.get()
        self.assertEqual(restored_review.reviewer_user_id, "existing")
        self.assertEqual(restored_review.submitter_user_id, "member")
