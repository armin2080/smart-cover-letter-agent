"""Cover letter routes, mounted at `/api/cover-letters/`."""

from django.urls import path

from .views import (
    CoverLetterDetailView,
    CoverLetterListCreateView,
    CoverLetterPdfView,
    CoverLetterPreviewView,
    CoverLetterRegenerateView,
)

urlpatterns = [
    path("", CoverLetterListCreateView.as_view(), name="cover-letter-list-create"),
    path("preview/", CoverLetterPreviewView.as_view(), name="cover-letter-preview"),
    path("<int:pk>/", CoverLetterDetailView.as_view(), name="cover-letter-detail"),
    path("<int:pk>/regenerate/", CoverLetterRegenerateView.as_view(), name="cover-letter-regenerate"),
    path("<int:pk>/pdf/", CoverLetterPdfView.as_view(), name="cover-letter-pdf"),
]
