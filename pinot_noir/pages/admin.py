from django.contrib import admin

from .models import PageMetadata


@admin.register(PageMetadata)
class PageMetadataAdmin(admin.ModelAdmin):
    list_display = ("slug", "enabled", "last_refreshed_at")
    list_editable = ("enabled",)
    search_fields = ("slug",)
