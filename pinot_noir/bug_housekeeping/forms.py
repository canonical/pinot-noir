from pathlib import Path

from django import forms
from django.core.exceptions import ValidationError

from .models import HousekeepingSettings

INPUT_CLASS = "p-form-validation__input"


class HousekeepingSettingsForm(forms.ModelForm):
    class Meta:
        model = HousekeepingSettings
        fields = ["repository", "working_directory"]
        labels = {
            "repository": "Saved-bugs Git repository",
            "working_directory": "Local checkout",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({"class": INPUT_CLASS, "autocomplete": "off"})

    def clean_working_directory(self) -> str:
        value = self.cleaned_data["working_directory"].strip()
        path = Path(value).expanduser()
        if path == Path(path.anchor or "."):
            raise ValidationError("Choose a dedicated subdirectory for the Git checkout.")
        return value
