from django.contrib import admin

from .forms import HousekeepingSettingsForm
from .models import HousekeepingReport, HousekeepingSettings


@admin.register(HousekeepingSettings)
class HousekeepingSettingsAdmin(admin.ModelAdmin):
    form = HousekeepingSettingsForm
    list_display = ("repository", "working_directory")

    def has_add_permission(self, request):
        return super().has_add_permission(request) and not HousekeepingSettings.objects.exists()


@admin.register(HousekeepingReport)
class HousekeepingReportAdmin(admin.ModelAdmin):
    list_display = ("team", "saved_bugs_file", "commit_hash", "pushed", "generated_at")
    readonly_fields = (
        "team",
        "html",
        "filename",
        "saved_bugs_file",
        "failed_sources",
        "commit_hash",
        "pushed",
        "git_error",
        "generated_at",
    )

    def has_add_permission(self, request):
        return False
