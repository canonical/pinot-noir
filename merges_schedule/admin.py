from django.contrib import admin
from .models import Merge


@admin.register(Merge)
class MergeAdmin(admin.ModelAdmin):
	list_display = ("package", "type", "milestone", "assignee", "status", "created_at")
	list_filter = ("type", "status", "milestone")
	search_fields = ("package", "assignee", "milestone")
