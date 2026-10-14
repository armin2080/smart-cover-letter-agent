from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import CvDocument, NotificationSettings, Preferences, Profile, ProfileSection, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("-created_at",)
    list_display = ("email", "full_name", "is_staff", "is_active", "created_at")
    list_filter = ("is_staff", "is_active")
    search_fields = ("email", "full_name")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("full_name",)}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Dates", {"fields": ("last_login", "created_at", "updated_at")}),
    )
    readonly_fields = ("created_at", "updated_at")
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "full_name", "password1", "password2", "is_staff", "is_active"),
            },
        ),
    )


class ProfileSectionInline(admin.TabularInline):
    model = ProfileSection
    fk_name = "user"
    extra = 0
    fields = ("key", "title", "content", "order")


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "location", "phone", "updated_at")
    search_fields = ("user__email", "user__full_name")


@admin.register(ProfileSection)
class ProfileSectionAdmin(admin.ModelAdmin):
    list_display = ("key", "title", "user", "order", "updated_at")
    list_filter = ("key",)
    search_fields = ("title", "user__email", "content")
    ordering = ("user", "order")


@admin.register(CvDocument)
class CvDocumentAdmin(admin.ModelAdmin):
    list_display = ("file_name", "user", "status", "size_bytes", "uploaded_at")
    list_filter = ("status",)
    search_fields = ("file_name", "user__email")


@admin.register(Preferences)
class PreferencesAdmin(admin.ModelAdmin):
    list_display = ("user", "radius_km", "updated_at")
    search_fields = ("user__email",)


@admin.register(NotificationSettings)
class NotificationSettingsAdmin(admin.ModelAdmin):
    list_display = ("user", "new_matches", "search_completed", "search_failures")
    search_fields = ("user__email",)
