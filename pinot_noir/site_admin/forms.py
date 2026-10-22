import hashlib

from django import forms
from django.core.validators import RegexValidator
from launchpadlib.credentials import Credentials

from pinot_noir.data_manager.models import UserTokens
from pinot_noir.launchpad.models import LPUser

# (field, label, help text). Help is about what each token is for and what it needs.
# lp_token is a multi-line credentials file, so it gets a textarea (MULTILINE).
TOKENS = (
    (
        "lp_token",
        "Launchpad",
        "The contents of a launchpadlib credentials file, starting with [1]. Used for "
        "every Launchpad query, bug filing and bug triage.",
    ),
    (
        "github_token",
        "GitHub",
        "GitHub data for bug triage (issues, pull requests, team members). Any token "
        "raises the rate limit for public repos. Private repos need Issues and Pull "
        "requests: Read; team lookups need organization Members: Read.",
    ),
    (
        "copilot_token",
        "GitHub Copilot",
        "Bug triage AI with the Copilot provider. A fine-grained token owned by your "
        "personal account with Copilot Requests: Read. Classic ghp_ tokens are rejected "
        "by Copilot.",
    ),
    (
        "openrouter_api_key",
        "OpenRouter",
        "Bug triage AI with the OpenRouter provider.",
    ),
)

MULTILINE = {"lp_token"}


class TokensForm(forms.Form):
    """Set or clear the current user's tokens without ever sending them back to the browser.

    A blank input keeps the stored value; the clear checkbox removes it.
    """

    def __init__(self, *args, instance: UserTokens, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance = instance
        for name, label, help_text in TOKENS:
            self.fields[name] = forms.CharField(
                label=label,
                help_text=help_text,
                required=False,
                strip=True,
                widget=forms.PasswordInput(
                    render_value=False, attrs={"autocomplete": "off", "spellcheck": "false"}
                ),
            )
            self.fields[f"clear_{name}"] = forms.BooleanField(label="Remove", required=False)

    def token_rows(self) -> list[dict]:
        return [
            {
                "field": self[name],
                "clear": self[f"clear_{name}"],
                "is_set": bool(getattr(self.instance, name)),
                "multiline": name in MULTILINE,
            }
            for name, _label, _help in TOKENS
        ]

    def clean_lp_token(self):
        value = self.cleaned_data["lp_token"]
        if value:
            try:
                Credentials.from_string(value)
            except Exception:
                raise forms.ValidationError("This is not a Launchpad credentials string.")
        return value

    def clean_copilot_token(self):
        value = self.cleaned_data["copilot_token"]
        if value.startswith("ghp_"):
            raise forms.ValidationError(
                "Copilot does not accept classic tokens; use a fine-grained token."
            )
        return value

    def clean(self):
        cleaned = super().clean() or {}
        for name, _label, _help in TOKENS:
            if cleaned.get(name) and cleaned.get(f"clear_{name}"):
                self.add_error(name, "Enter a new value or remove it, not both.")
        return cleaned

    def save(self) -> list[str]:
        """Apply the changes; return the labels of the tokens that changed."""
        changed = []
        for name, label, _help in TOKENS:
            if self.cleaned_data[f"clear_{name}"]:
                if getattr(self.instance, name):
                    setattr(self.instance, name, "")
                    changed.append(label)
            elif self.cleaned_data[name]:
                setattr(self.instance, name, self.cleaned_data[name])
                changed.append(label)
        if changed:
            self.instance.save()
        return changed


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
