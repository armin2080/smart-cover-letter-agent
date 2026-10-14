"""Profile, preferences and account routes, mounted at `/api/`."""

from django.urls import path

from .views import (
    AccountDeleteView,
    CvUploadView,
    NotificationSettingsView,
    PreferencesView,
    ProfileSectionDetailView,
    ProfileView,
)

urlpatterns = [
    path("profile/", ProfileView.as_view(), name="profile"),
    path("profile/sections/<str:section_id>/", ProfileSectionDetailView.as_view(), name="profile-section"),
    path("profile/cv/", CvUploadView.as_view(), name="profile-cv"),
    path("profile/preferences/", PreferencesView.as_view(), name="profile-preferences"),
    path("settings/notifications/", NotificationSettingsView.as_view(), name="settings-notifications"),
    path("account/", AccountDeleteView.as_view(), name="account-delete"),
]
