import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models


def _build_fernet() -> Fernet:
    """Build a deterministic Fernet from settings.FIELD_ENCRYPTION_KEY."""
    key_material = hashlib.sha256(settings.FIELD_ENCRYPTION_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(key_material))


class EncryptedTextField(models.TextField):
    """A text field that stores encrypted values in the database."""

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value in (None, ""):
            return value
        encrypted = _build_fernet().encrypt(value.encode("utf-8"))
        return encrypted.decode("utf-8")

    def from_db_value(self, value, expression, connection):
        return self.to_python(value)

    def to_python(self, value):
        value = super().to_python(value)
        if value in (None, ""):
            return value
        try:
            decrypted = _build_fernet().decrypt(value.encode("utf-8"))
            return decrypted.decode("utf-8")
        except (InvalidToken, ValueError):
            # Keep legacy unencrypted rows readable until they are saved again.
            return value
