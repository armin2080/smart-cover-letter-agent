"""Job routes, mounted at `/api/jobs/`."""

from django.urls import path

from .views import (
    JobCountsView,
    JobDetailView,
    JobDismissView,
    JobListView,
    JobRecentView,
    JobRestoreView,
    JobReviewView,
    JobSaveView,
    JobStatsView,
    ManualJobImportView,
    ProviderStatusView,
)

urlpatterns = [
    # Literal segments must precede the <int:pk> pattern.
    path("", JobListView.as_view(), name="job-list"),
    path("counts/", JobCountsView.as_view(), name="job-counts"),
    path("stats/", JobStatsView.as_view(), name="job-stats"),
    path("recent/", JobRecentView.as_view(), name="job-recent"),
    path("providers/", ProviderStatusView.as_view(), name="job-providers"),
    path("import/", ManualJobImportView.as_view(), name="job-import"),
    path("<int:pk>/", JobDetailView.as_view(), name="job-detail"),
    # Independent user actions.
    path("<int:pk>/review/", JobReviewView.as_view(), name="job-review"),
    path("<int:pk>/save/", JobSaveView.as_view(), name="job-save"),
    path("<int:pk>/dismiss/", JobDismissView.as_view(), name="job-dismiss"),
    path("<int:pk>/restore/", JobRestoreView.as_view(), name="job-restore"),
]
