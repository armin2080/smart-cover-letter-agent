from django.contrib import admin

from .models import ActivityEntry, Job


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("title", "company", "user", "match", "status", "source", "posted_at")
    list_filter = ("match", "status", "source", "employment_type")
    search_fields = ("title", "company", "user__email")
    date_hierarchy = "posted_at"
    readonly_fields = ("created_at", "updated_at", "fingerprint")


@admin.register(ActivityEntry)
class ActivityEntryAdmin(admin.ModelAdmin):
    list_display = ("kind", "title", "user", "occurred_at")
    list_filter = ("kind",)
    search_fields = ("title", "user__email")
    date_hierarchy = "occurred_at"
