from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.db import connection
from django.test import RequestFactory, TestCase

from pinot_noir.data_manager.admin import UserTokensAdmin
from pinot_noir.data_manager.models import UserTokens


class UserTokensAdminTests(TestCase):
    def setUp(self):
        self.site = AdminSite()
        self.model_admin = UserTokensAdmin(UserTokens, self.site)
        self.request_factory = RequestFactory()
        self.user = User.objects.create_user(username="alice", password="pw", is_staff=True)
        self.other_user = User.objects.create_user(username="bob", password="pw", is_staff=True)
        self.tokens = UserTokens.objects.create(user=self.user, lp_token="alice-secret")
        self.other_tokens = UserTokens.objects.create(user=self.other_user, lp_token="bob-secret")

    def test_queryset_only_contains_request_users_tokens(self):
        request = self.request_factory.get("/admin/data_manager/usertokens/")
        request.user = self.user

        queryset = self.model_admin.get_queryset(request)

        self.assertEqual(list(queryset), [self.tokens])

    def test_change_permission_denies_other_users_record(self):
        request = self.request_factory.get("/admin/data_manager/usertokens/")
        request.user = self.user

        self.assertTrue(self.model_admin.has_change_permission(request, self.tokens))
        self.assertFalse(self.model_admin.has_change_permission(request, self.other_tokens))

    def test_user_can_only_add_when_their_record_does_not_exist(self):
        request = self.request_factory.get("/admin/data_manager/usertokens/")
        request.user = self.user
        other_request = self.request_factory.get("/admin/data_manager/usertokens/")
        other_request.user = User.objects.create_user(
            username="charlie", password="pw", is_staff=True
        )

        self.assertFalse(self.model_admin.has_add_permission(request))
        self.assertTrue(self.model_admin.has_add_permission(other_request))


class UserTokensEncryptionTests(TestCase):
    def test_token_is_encrypted_in_database(self):
        user = User.objects.create_user(username="token-user", password="pw", is_staff=True)
        UserTokens.objects.create(user=user, lp_token="plain-token")

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT lp_token FROM data_manager_usertokens WHERE user_id = %s", [user.id]
            )
            db_token = cursor.fetchone()[0]

        self.assertNotEqual(db_token, "plain-token")

        # ORM reads should transparently decrypt.
        self.assertEqual(UserTokens.objects.get(user=user).lp_token, "plain-token")
