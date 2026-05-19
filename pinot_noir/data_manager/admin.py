import json

from django.contrib import admin, messages
from django.contrib.sites.models import Site
from django.http import HttpResponse

from pinot_noir.data_manager.tasks import (
    bug_submission_to_json_dict,
    prepare_merge_bug_submissions_for_user,
    submit_prepared_merge_bug_submissions_for_user,
)

from .models import (
    BackportBugFilterSettings,
    BackportBugPackageInfo,
    LPReviewMarkerUser,
    MergeBugFilterSettings,
    MergeBugPackageInfo,
    UserTokens,
)


@admin.register(UserTokens)
class UserTokensAdmin(admin.ModelAdmin):
    list_display = ("user", "masked_lp_token")
    search_fields = ("user__username",)
    readonly_fields = ("user",)

    @admin.display(description="lp_token")
    def masked_lp_token(self, obj):
        if not obj.lp_token:
            return ""
        return "********"

    def get_queryset(self, request):
        return super().get_queryset(request).filter(user=request.user)

    def has_view_permission(self, request, obj=None):
        if obj is None:
            return request.user.is_staff
        return obj.user_id == request.user.id

    def has_change_permission(self, request, obj=None):
        if obj is None:
            return request.user.is_staff
        return obj.user_id == request.user.id

    def has_delete_permission(self, request, obj=None):
        if obj is None:
            return request.user.is_staff
        return obj.user_id == request.user.id

    def has_add_permission(self, request):
        if not request.user.is_staff:
            return False
        return not UserTokens.objects.filter(user=request.user).exists()

    def save_model(self, request, obj, form, change):
        obj.user = request.user
        super().save_model(request, obj, form, change)


@admin.register(MergeBugPackageInfo)
class MergeBugPackageInfoAdmin(admin.ModelAdmin):
    list_display = ("package", "milestone_offset", "bug_filed_this_cycle")
    search_fields = ("package",)
    actions = ["prepare_merge_bugs_download_json", "prepare_and_submit_merge_bugs"]

    @admin.action(description="Prepare merge bug submissions and download as JSON")
    def prepare_merge_bugs_download_json(self, request, queryset):
        try:
            submissions = prepare_merge_bug_submissions_for_user(user=request.user)
        except Exception as exc:
            self.message_user(request, f"Failed to prepare submissions: {exc}", messages.ERROR)
            return

        if not submissions:
            self.message_user(request, "No new merge bug submissions needed.", messages.WARNING)
            return

        payload = [
            {"package": pkg, "submission": bug_submission_to_json_dict(sub)}
            for pkg, sub in submissions
        ]
        response = HttpResponse(
            json.dumps(payload, indent=2, sort_keys=True),
            content_type="application/json",
        )
        response["Content-Disposition"] = 'attachment; filename="merge_bug_submissions.json"'
        return response

    @admin.action(description="Prepare and submit merge bugs to Launchpad")
    def prepare_and_submit_merge_bugs(self, request, queryset):
        try:
            submissions = prepare_merge_bug_submissions_for_user(user=request.user)
        except Exception as exc:
            self.message_user(request, f"Failed to prepare submissions: {exc}", messages.ERROR)
            return

        if not submissions:
            self.message_user(request, "No new merge bug submissions needed.", messages.WARNING)
            return

        try:
            submitted, failed = submit_prepared_merge_bug_submissions_for_user(
                user=request.user, submissions=submissions
            )
        except Exception as exc:
            self.message_user(request, f"Failed to submit bugs: {exc}", messages.ERROR)
            return

        level = messages.SUCCESS if failed == 0 else messages.WARNING
        self.message_user(
            request,
            f"Submitted {submitted} merge bug(s); {failed} failed.",
            level,
        )


@admin.register(BackportBugPackageInfo)
class BackportBugPackageInfoAdmin(admin.ModelAdmin):
    list_display = ("name", "milestone_offset", "package_names_combined", "bug_filed_this_cycle")
    search_fields = ("name", "package_names_combined")


@admin.register(LPReviewMarkerUser)
class LPReviewMarkerUserAdmin(admin.ModelAdmin):
    list_display = ("username",)
    search_fields = ("username",)


@admin.register(MergeBugFilterSettings)
class MergeBugFilterSettingsAdmin(admin.ModelAdmin):
    list_display = ("tags_combined", "subscribers_combined")
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

    def get_queryset(self, request):
        return (
            super().get_queryset(request).filter(settings_type=MergeBugFilterSettings.TYPE_MERGE)
        )

    def save_model(self, request, obj, form, change):
        obj.site = Site.objects.get_current()
        obj.settings_type = MergeBugFilterSettings.TYPE_MERGE
        super().save_model(request, obj, form, change)


@admin.register(BackportBugFilterSettings)
class BackportBugFilterSettingsAdmin(admin.ModelAdmin):
    list_display = ("tags_combined", "subscribers_combined")
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
        obj.settings_type = MergeBugFilterSettings.TYPE_BACKPORT
        super().save_model(request, obj, form, change)
