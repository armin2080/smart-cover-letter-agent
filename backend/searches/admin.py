from django.contrib import admin

from .models import AutoSearchSettings, SearchRun


@admin.register(SearchRun)
class SearchRunAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "mode", "status", "discovered", "matched", "started_at", "finished_at")
    list_filter = ("mode", "status")
    search_fields = ("user__email", "criteria_summary")
    date_hierarchy = "started_at"
    readonly_fields = ("started_at", "finished_at", "stages", "criteria")


@admin.register(AutoSearchSettings)
class AutoSearchSettingsAdmin(admin.ModelAdmin):
    list_display = ("user", "enabled", "frequency", "time_of_day", "last_run_at", "next_run_at")
    list_filter = ("enabled", "frequency")
    search_fields = ("user__email",)
