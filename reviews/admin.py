from django.contrib import admin

from .models import Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "package",
        "release_version",
        "reviewer_user",
        "submitter_user",
        "status",
        "created_at",
    )
    list_filter = ("status", "release_version")
    search_fields = (
        "package",
        "release_version",
        "reviewer",
        "reviewer_user__username",
        "submitter",
        "submitter_user__username",
    )
