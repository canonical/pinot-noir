from django.contrib import admin

from .models import ReviewMarker, UbuntuRelease


@admin.register(ReviewMarker)
class ReviewMarkerAdmin(admin.ModelAdmin):
    list_display = ("username",)
    search_fields = ("username",)


@admin.register(UbuntuRelease)
class UbuntuReleaseAdmin(admin.ModelAdmin):
    list_display = ("adjective", "animal", "version", "status")
    search_fields = ("adjective", "animal", "version", "status")
