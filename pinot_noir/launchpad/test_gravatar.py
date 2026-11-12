import hashlib

from django.contrib.auth.models import User
from django.test import SimpleTestCase

from .gravatar import gravatar_url


class GravatarTests(SimpleTestCase):
    def test_uses_normalized_django_email(self):
        user = User(username="alice", email="  Alice@Example.COM  ")
        email_hash = hashlib.md5(b"alice@example.com", usedforsecurity=False).hexdigest()
        self.assertEqual(gravatar_url(user), f"https://www.gravatar.com/avatar/{email_hash}")

    def test_no_email_has_no_gravatar(self):
        self.assertEqual(gravatar_url(User(username="alice")), "")
