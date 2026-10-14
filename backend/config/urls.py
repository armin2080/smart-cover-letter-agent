"""Root URL configuration.

All application endpoints live under `/api/` to match the frontend contract.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("accounts.urls_auth")),
    path("api/", include("accounts.urls_profile")),
    path("api/jobs/", include("jobs.urls")),
    path("api/", include("jobs.urls_activity")),
    path("api/searches/", include("searches.urls")),
    path("api/cover-letters/", include("cover_letters.urls")),
    # OpenAPI schema + interactive docs
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

admin.site.site_header = "Smart Cover Letter Agent"
admin.site.site_title = "Smart Cover Letter Agent"
admin.site.index_title = "Backoffice"
