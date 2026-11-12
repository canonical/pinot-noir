from django.conf import settings
from django.db import models


class Preferences(models.Model):
    """Preferences owned by one user, independent of staff permissions."""

    class Theme(models.TextChoices):
        LIGHT = "light", "Light"
        DARK = "dark", "Dark"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="preferences",
    )
    theme = models.CharField(max_length=5, choices=Theme.choices, default=Theme.LIGHT)

    def __str__(self):
        return f"{self.user.get_username()}'s preferences"
