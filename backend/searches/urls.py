"""Search routes, mounted at `/api/searches/`."""

from django.urls import path

from .views import (
    AutoSearchSettingsView,
    SearchRunCancelView,
    SearchRunDetailView,
    SearchRunListCreateView,
)

urlpatterns = [
    path("", SearchRunListCreateView.as_view(), name="search-list-create"),
    path("settings/", AutoSearchSettingsView.as_view(), name="search-settings"),
    path("<int:pk>/", SearchRunDetailView.as_view(), name="search-detail"),
    path("<int:pk>/cancel/", SearchRunCancelView.as_view(), name="search-cancel"),
]
