from django.contrib import admin

from .models import CoverLetter


@admin.register(CoverLetter)
class CoverLetterAdmin(admin.ModelAdmin):
    list_display = ("id", "job", "user", "status", "tone", "length", "generator", "updated_at")
    list_filter = ("status", "tone", "length", "generator")
    search_fields = ("job__title", "job__company", "user__email")
    readonly_fields = ("created_at", "updated_at", "saved_at", "generator")
