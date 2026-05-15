from django.contrib import admin
from django.contrib.sites.models import Site

from .models import (
    BackportBugFilterSettings,
    LPReviewMarkerUser,
    MergeBugFilterSettings,
    UserTokens,
)


@admin.register(UserTokens)
class UserTokensAdmin(admin.ModelAdmin):
    list_display = ("user", "lp_token")
    search_fields = ("user__username",)


@admin.register(LPReviewMarkerUser)
class LPReviewMarkerUserAdmin(admin.ModelAdmin):
    list_display = ("username",)
    search_fields = ("username",)


@admin.register(MergeBugFilterSettings)
class MergeBugFilterSettingsAdmin(admin.ModelAdmin):
    list_display = ("site", "tags_combined", "subscribers_combined")
    fieldsets = (
        (
            "Bug filters",
            {
                "fields": ("tags_combined", "subscribers_combined"),
                "description": (
                    "Comma-separated lists of tags and subscribers "
                    "that merge board bugs must have."
                ),
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        obj.site = Site.objects.get_current()
        super().save_model(request, obj, form, change)


@admin.register(BackportBugFilterSettings)
class BackportBugFilterSettingsAdmin(admin.ModelAdmin):
    list_display = ("site", "tags_combined", "subscribers_combined")
    fieldsets = (
        (
            "Bug filters",
            {
                "fields": ("tags_combined", "subscribers_combined"),
                "description": (
                    "Comma-separated lists of tags and subscribers "
                    "that merge board backport bugs must have."
                ),
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        obj.site = Site.objects.get_current()
        super().save_model(request, obj, form, change)
