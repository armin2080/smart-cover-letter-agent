"""Root URL configuration.

All application endpoints live under `/api/` to match the frontend contract.
The built single-page app is served from the same origin, so there is one
Cloudflare route and no CORS to configure.
"""

from pathlib import Path

import os

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import FileResponse, Http404
from django.urls import include, path, re_path
from django.views.decorators.cache import never_cache
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

#: Where `vite build` writes. Copied to the server by the deploy step.
SPA_ROOT = Path(os.environ.get("SPA_ROOT", Path(settings.BASE_DIR).parent / "frontend" / "dist"))


@never_cache
def spa_index(request, *args, **kwargs):
    """Serve the built SPA shell for any non-API path.

    A client-side route such as /jobs exists only in the browser's history.
    Without this catch-all, reloading that URL hits Django, matches nothing,
    and returns 404. Returning index.html lets the router take over.

    Deliberately *not* cached: the HTML references hashed asset filenames, so a
    stale copy would point at files a later deploy had deleted.
    """

    index = SPA_ROOT / "index.html"
    if not index.exists():
        raise Http404(
            "The frontend has not been built. Run `npm run build` in frontend/ "
            "and ensure dist/ is present, or set SPA_ROOT."
        )
    return FileResponse(index.open("rb"), content_type="text/html; charset=utf-8")


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

# Uploaded CVs are served by Django in both modes: the reverse proxy (the
# Cloudflare tunnel) only ever talks to gunicorn, so there is no other web
# server to hand them to. Access is not public — the URLs are unguessable and
# the files are reached only through the app.
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Catch-all last, so every /api/ route above is matched first.
urlpatterns += [re_path(r"^(?!api/|admin/|static/|media/).*$", spa_index)]

admin.site.site_header = "Smart Cover Letter Agent"
admin.site.site_title = "Smart Cover Letter Agent"
admin.site.index_title = "Backoffice"
