from django import forms
from django.contrib.auth.models import User
from django.core.validators import RegexValidator

from pinot_noir.data_manager.models import TeamSettings
from pinot_noir.launchpad.models import ReviewMarker

# Launchpad user names: lowercase letters, digits, and + - . (not first).
LP_NAME = RegexValidator(r"^[a-z0-9][a-z0-9+.-]*$", "Enter a Launchpad user name.")


class LaunchpadUsernameForm(forms.Form):
    username = forms.CharField(label="Launchpad user name", max_length=100)

    def clean_username(self):
        # Accept ~name and capitals as pasted from Launchpad URLs, then validate.
        username = self.cleaned_data["username"].strip().lstrip("~").lower()
        LP_NAME(username)
        return username


class RoleForm(LaunchpadUsernameForm):
    def save(self) -> tuple[User | ReviewMarker, bool]:
        raise NotImplementedError


class TeamMemberForm(RoleForm):
    """Create, reactivate, or update a Django user used as a Launchpad team member."""

    username = forms.CharField(
        label="Username",
        max_length=100,
        help_text="Also used as the Launchpad username.",
    )
    email = forms.EmailField(
        label="Email (optional)",
        required=False,
        help_text="Used for Google sign-in and Gravatar.",
    )

    def save(self) -> tuple[User, bool]:
        username = self.cleaned_data["username"]
        email = self.cleaned_data["email"].strip()
        user = User.objects.filter(username=username).first()
        if user is None:
            return User.objects.create_user(username=username, email=email), False
        already_active = user.is_active
        user.is_active = True
        if email:
            user.email = email
        user.save(update_fields=["is_active", "email"])
        return user, already_active


class ReviewMarkerForm(RoleForm):
    """Create a review-marker username independently of Django accounts."""

    def save(self) -> tuple[ReviewMarker, bool]:
        marker, created = ReviewMarker.objects.get_or_create(
            username=self.cleaned_data["username"]
        )
        return marker, not created


class TeamNameForm(forms.ModelForm):
    class Meta:
        model = TeamSettings
        fields = ["name"]
        labels = {"name": "Team name"}

    def clean_name(self):
        return self.cleaned_data["name"].strip()
