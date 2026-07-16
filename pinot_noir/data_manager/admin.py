from django.contrib import admin, messages
from django.contrib.sites.models import Site

from pinot_noir.data_manager.tasks import (
    prepare_merge_bug_submissions,
    submit_prepared_merge_bug_submissions,
)

from .models import (
    BackportBugFilterSettings,
    BackportBugPackageInfo,
    MergeBugFilterSettings,
    MergeBugPackageInfo,
    UserTokens,
    WeeklyTask,
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
    actions = ["prepare_and_submit_merge_bugs"]

    @admin.action(description="Prepare and submit merge bugs to Launchpad")
    def prepare_and_submit_merge_bugs(self, request, queryset):
        try:
            submissions = prepare_merge_bug_submissions(user=request.user)
        except Exception as exc:
            self.message_user(request, f"Failed to prepare submissions: {exc}", messages.ERROR)
            return

        if not submissions:
            self.message_user(request, "No new merge bug submissions needed.", messages.WARNING)
            return

        try:
            submitted, failed = submit_prepared_merge_bug_submissions(
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


@admin.register(WeeklyTask)
class WeeklyTaskAdmin(admin.ModelAdmin):
    list_display = ("task", "user", "active_days_display", "time_of_day", "enabled", "next_run")
    list_filter = ("enabled", "task")
    readonly_fields = ("next_run",)

    @admin.display(description="Days")
    def active_days_display(self, obj):
        return obj.active_days_display()
