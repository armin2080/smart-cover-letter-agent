"""Profile, preferences and account routes, mounted at `/api/`."""

from django.urls import path

from .views import (
    AccountDeleteView,
    CvUploadView,
    NotificationSettingsView,
    PreferencesView,
    ProfileSectionDetailView,
    ProfileView,
    PublicConfigView,
    TourCompletedView,
)

urlpatterns = [
    # Public: read by the login screen before anyone is authenticated.
    path("config/", PublicConfigView.as_view(), name="public-config"),
    path("profile/", ProfileView.as_view(), name="profile"),
    path("profile/tour-completed/", TourCompletedView.as_view(), name="profile-tour-completed"),
    path("profile/sections/<str:section_id>/", ProfileSectionDetailView.as_view(), name="profile-section"),
    path("profile/cv/", CvUploadView.as_view(), name="profile-cv"),
    path("profile/preferences/", PreferencesView.as_view(), name="profile-preferences"),
    path("settings/notifications/", NotificationSettingsView.as_view(), name="settings-notifications"),
    path("account/", AccountDeleteView.as_view(), name="account-delete"),
]
