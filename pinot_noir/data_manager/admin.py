from django.contrib import admin

from .models import LPReviewMarkerUser, UserTokens


@admin.register(UserTokens)
class UserTokensAdmin(admin.ModelAdmin):
    list_display = ("user", "lp_token")
    search_fields = ("user__username",)


@admin.register(LPReviewMarkerUser)
class LPReviewMarkerUserAdmin(admin.ModelAdmin):
    list_display = ("username",)
    search_fields = ("username",)
