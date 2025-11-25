from django import forms
from django.contrib import admin
from django.utils.safestring import mark_safe
import hashlib

from .models import LPUser


class LPUserAdminForm(forms.ModelForm):
    # Admin-only helper field: accept an email and compute email_md5 on save
    email = forms.EmailField(required=False, help_text="Optional: enter an email to compute MD5 for Gravatar")

    class Meta:
        model = LPUser
        fields = ["username", "email_md5"]

    def save(self, commit=True):
        instance = super().save(commit=False)
        email = self.cleaned_data.get("email")
        if email:
            md5 = hashlib.md5(email.strip().lower().encode("utf-8")).hexdigest()
            instance.email_md5 = md5
        if commit:
            instance.save()
        return instance


@admin.register(LPUser)
class LPUserAdmin(admin.ModelAdmin):
    form = LPUserAdminForm
    list_display = ("username", "email_md5", "gravatar_preview")
    search_fields = ("username",)
    readonly_fields = ("email_md5", "gravatar_preview")
    fields = ("username", "email", "email_md5", "gravatar_preview")

    def gravatar_preview(self, obj):
        if not obj or not obj.email_md5:
            return ""
        url = f"https://www.gravatar.com/avatar/{obj.email_md5}?s=48&d=identicon"
        return mark_safe(f"<img src=\"{url}\" alt=\"{obj.username}\" width=\"48\" height=\"48\" />")

    gravatar_preview.short_description = "Gravatar"
