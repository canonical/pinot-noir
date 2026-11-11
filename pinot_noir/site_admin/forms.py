import hashlib

from django import forms
from django.core.validators import RegexValidator

from pinot_noir.data_manager.models import TeamSettings
from pinot_noir.launchpad.models import LPUser

# Launchpad user names: lowercase letters, digits, and + - . (not first).
LP_NAME = RegexValidator(r"^[a-z0-9][a-z0-9+.-]*$", "Enter a Launchpad user name.")


class LPUserRoleForm(forms.Form):
    """Add a Launchpad user to one role (team member or review marker)."""

    username = forms.CharField(label="Launchpad user name", max_length=100)
    email = forms.EmailField(
        label="Email (optional)",
        required=False,
        help_text="Only used to show their Gravatar; just its MD5 hash is stored.",
    )

    def clean_username(self):
        # Accept ~name and capitals as pasted from Launchpad URLs, then validate.
        username = self.cleaned_data["username"].strip().lstrip("~").lower()
        LP_NAME(username)
        return username

    def save(self, role: str) -> tuple[LPUser, bool]:
        """Set *role* on the user, creating it if needed. Return (user, was_already_set)."""
        user, _ = LPUser.objects.get_or_create(username=self.cleaned_data["username"])
        already = getattr(user, role)
        setattr(user, role, True)
        if email := self.cleaned_data.get("email"):
            user.email_md5 = hashlib.md5(email.strip().lower().encode("utf-8")).hexdigest()
        user.save()
        return user, already


class ReviewMarkerForm(LPUserRoleForm):
    """Review markers are often teams and never shown with an avatar: no email."""

    email = None


class TeamNameForm(forms.ModelForm):
    class Meta:
        model = TeamSettings
        fields = ["name"]
        labels = {"name": "Team name"}

    def clean_name(self):
        return self.cleaned_data["name"].strip()
