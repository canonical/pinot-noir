from django.contrib import admin

from .models import LPUser


@admin.register(LPUser)
class LPUserAdmin(admin.ModelAdmin):
    list_display = ("username", "email_md5")
    search_fields = ("username",)
