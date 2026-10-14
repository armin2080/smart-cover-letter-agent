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
from django.views.static import serve as static_serve
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

#: Where `vite build` writes. Copied to the server by the deploy step.
SPA_ROOT = Path(os.environ.get("SPA_ROOT", Path(settings.BASE_DIR).parent / "frontend" / "dist"))


@never_cache
def spa_shell(request):
    """Serve the built SPA shell.

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


def spa(request, path=""):
    """Serve a real build artefact if one exists, else the SPA shell.

    Two different kinds of request arrive here and they need opposite answers:

    * A file the build produced — `/assets/index-<hash>.js`, `favicon.svg`.
      These must be returned as themselves. Vite hashes the filenames, so they
      can be cached indefinitely.
    * A client-side route — `/jobs`, `/profile`. These exist only in browser
      history; there is no file. Returning the shell lets the router take over,
      instead of 404ing on reload.

    An earlier version used an exclusion list of URL prefixes and served the
    shell for everything else. That missed `/assets/`, so the JavaScript bundle
    was answered with HTML: status 200, `Content-Type: text/html`, and a blank
    page in the browser. Checking whether the file exists removes the need to
    keep such a list correct.
    """

    if path:
        candidate = SPA_ROOT / path
        if candidate.is_file():
            # `serve` handles content types and refuses path traversal, so a
            # crafted path cannot escape the build directory.
            response = static_serve(request, path, document_root=str(SPA_ROOT))
            if path.startswith("assets/"):
                # Content-addressed by the build, so this exact URL can never
                # refer to different bytes.
                response["Cache-Control"] = "public, max-age=31536000, immutable"
            return response

    return spa_shell(request)


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

def serve_media(request, path):
    """Serve an uploaded file from `MEDIA_ROOT`.

    `MEDIA_ROOT` is read here rather than passed as `document_root` at import
    time. Binding it into the URL pattern would freeze the value at startup, so
    anything that changes it later — tests, or an operator relocating the
    directory — would silently keep serving the original path.
    """

    return static_serve(request, path, document_root=str(settings.MEDIA_ROOT))


# Uploaded CVs. Registered explicitly rather than through
# `django.conf.urls.static.static()`, which returns an empty list whenever DEBUG
# is false — so the obvious version of this added no route at all in production
# and uploads could not be downloaded.
urlpatterns += [re_path(r"^media/(?P<path>.*)$", serve_media, name="media")]

# Catch-all last, so every route above is matched first.
#
# The lookahead matches a reserved word followed by `/` or end-of-string, not a
# bare prefix and not a word boundary:
#   * `admin/` alone let the bare `/admin` through, so the URL resolved,
#     `APPEND_SLASH` never fired, and the browser got an empty 200 instead of a
#     redirect to `/admin/`.
#   * `\b` fixed that but also swallowed `/static-assets`, because a hyphen is a
#     word boundary.
# Requiring `/` or `$` excludes exactly the reserved namespaces and leaves
# every client-side route — `/administration`, `/static-assets` — to the SPA.
urlpatterns += [re_path(r"^(?!(?:api|admin|static|media)(?:/|$))(?P<path>.*)$", spa)]

admin.site.site_header = "Smart Cover Letter Agent"
admin.site.site_title = "Smart Cover Letter Agent"
admin.site.index_title = "Backoffice"
