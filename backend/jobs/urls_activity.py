"""Activity routes, mounted at `/api/`."""

from django.urls import path

from .views import ActivityListView

urlpatterns = [
    path("activity/", ActivityListView.as_view(), name="activity-list"),
]
