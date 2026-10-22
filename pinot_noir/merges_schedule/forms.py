import re

from django import forms
from django.contrib.sites.models import Site
from django.core.exceptions import ValidationError

from pinot_noir.data_manager.models import MergeBugFilterSettings
from pinot_noir.site_admin.forms import LP_NAME

LP_TAG = re.compile(r"^[a-z0-9][a-z0-9+.-]*$")

# MergeBugFilterSettings list field -> (label, singular for messages)
FIELDS = {
    "tags": ("Tags", "tag"),
    "subscribers": ("Subscribers", "subscriber"),
}


def get_filter_settings(settings_type: str) -> MergeBugFilterSettings | None:
    return MergeBugFilterSettings.objects.filter(settings_type=settings_type).first()


class FilterEntryForm(forms.Form):
    """Add one tag or subscriber to a bug filter (merge or backport)."""

    value = forms.CharField(max_length=100)

    def __init__(self, *args, settings_type: str, field: str, **kwargs):
        self.settings_type = settings_type
        self.field = field
        super().__init__(*args, prefix=f"{settings_type}-{field}", **kwargs)
        _, singular = FIELDS[field]
        value = self.fields["value"]
        value.label = f"Add {singular}"
        value.widget.attrs.update({"class": "p-form-validation__input", "autocomplete": "off"})

    def clean_value(self) -> str:
        value = self.cleaned_data["value"].strip().lower()
        if self.field == "tags":
            if not LP_TAG.match(value):
                raise ValidationError(
                    "Launchpad tags use lowercase letters, numbers, +, - and . only."
                )
        else:
            value = value.lstrip("~")
            LP_NAME(value)
        settings = get_filter_settings(self.settings_type)
        if settings is not None and value in getattr(settings, self.field):
            raise ValidationError(f"{value} is already added.")
        if self.field == "subscribers" and not (settings and settings.tags):
            raise ValidationError("Add a tag first.")
        return value

    def save(self) -> str:
        settings = get_filter_settings(self.settings_type) or MergeBugFilterSettings(
            site=Site.objects.get_current(), settings_type=self.settings_type
        )
        value = self.cleaned_data["value"]
        setattr(settings, self.field, [*getattr(settings, self.field), value])
        settings.save()
        return value


def remove_filter_entry(settings_type: str, field: str, value: str) -> str | None:
    """Remove one entry; return an error message if it can't be removed.

    The last tag can't go while there are subscribers (filed bugs would have no
    tags). When both lists end up empty the row is deleted, so that bug type is
    no longer collected or filed.
    """
    settings = get_filter_settings(settings_type)
    if settings is None or value not in getattr(settings, field):
        return f"{value} isn't in the list."
    remaining = [entry for entry in getattr(settings, field) if entry != value]
    if field == "tags" and not remaining and settings.subscribers:
        return "Remove the subscribers before the last tag."
    setattr(settings, field, remaining)
    if not settings.tags and not settings.subscribers:
        settings.delete()
    else:
        settings.save()
    return None
