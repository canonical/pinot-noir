from django.contrib import admin

from .models import UserTokens


@admin.register(UserTokens)
class UserTokensAdmin(admin.ModelAdmin):
    list_display = ("user", "lp_token")
    search_fields = ("user__username",)
