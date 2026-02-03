from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    """Custom admin for User model with profile fields."""
    
    fieldsets = UserAdmin.fieldsets + (
        ('Profile Information', {
            'fields': ('experience', 'skills', 'certificates', 'preferred_jobs'),
        }),
    )
    
    list_display = ['username', 'email', 'first_name', 'last_name', 'is_staff']
