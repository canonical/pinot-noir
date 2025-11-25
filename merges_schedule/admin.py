from django.contrib import admin
from .models import Merge


@admin.register(Merge)
class MergeAdmin(admin.ModelAdmin):
	list_display = ("lp_bug", "package", "merge_type", "milestone", "assignee_user", "status", "created_at")
	list_filter = ("merge_type", "status", "milestone")
	search_fields = ("package", "assignee", "assignee_user__username", "milestone")
