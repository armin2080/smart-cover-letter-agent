"""Tests for SPA and static file serving.

These exist because of a real bug: an earlier catch-all served the SPA shell for
any path it did not recognise, and its exclusion list did not include
`/assets/`. The JavaScript bundle was therefore answered with `index.html` —
status 200, `Content-Type: text/html` — so the browser received HTML where it
expected JavaScript and rendered a blank page.

Every check here asserts the **content type**, not just the status code. A
status-only assertion would have passed against the broken version, which is how
the bug reached a deployment.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from django.test import TestCase, override_settings


class SpaServingTests(TestCase):
    """A built frontend is served file-by-file, with the shell as fallback."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # A stand-in build directory, so the tests do not depend on whether
        # `npm run build` has been run on this machine.
        cls._tmp = tempfile.TemporaryDirectory()
        cls.dist = Path(cls._tmp.name)

        (cls.dist / "index.html").write_text(
            "<!doctype html><html><body><div id=\"root\"></div></body></html>"
        )
        assets = cls.dist / "assets"
        assets.mkdir()
        (assets / "index-abc123.js").write_text("console.log('bundle')")
        (assets / "index-abc123.css").write_text(".a{color:red}")
        (cls.dist / "favicon.svg").write_text("<svg/>")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()
        super().tearDownClass()

    def setUp(self):
        self.override = override_settings(SPA_ROOT=self.dist)
        self.override.enable()
        # `config.urls` reads SPA_ROOT at import time, so patch the module
        # attribute the view actually closes over.
        import config.urls as urls_module

        self._original_root = urls_module.SPA_ROOT
        urls_module.SPA_ROOT = self.dist

    def tearDown(self):
        import config.urls as urls_module

        urls_module.SPA_ROOT = self._original_root
        self.override.disable()

    def _body(self, response) -> bytes:
        """Read a response body.

        File responses stream, so `.content` is unavailable — the bytes only
        exist as `streaming_content`.
        """

        if getattr(response, "streaming", False):
            return b"".join(response.streaming_content)
        return response.content

    def test_javascript_asset_is_not_served_as_html(self):
        """The regression. A status-only check would not catch this."""

        response = self.client.get("/assets/index-abc123.js")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("text/html", response["Content-Type"])
        self.assertEqual(self._body(response), b"console.log('bundle')")

    def test_stylesheet_asset_is_served_as_css(self):
        response = self.client.get("/assets/index-abc123.css")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("text/html", response["Content-Type"])
        self.assertEqual(self._body(response), b".a{color:red}")

    def test_hashed_assets_are_cached_immutably(self):
        """The build content-addresses these, so the URL can never change meaning."""

        response = self.client.get("/assets/index-abc123.js")
        self.assertIn("immutable", response["Cache-Control"])

    def test_a_root_level_file_is_served_directly(self):
        response = self.client.get("/favicon.svg")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("text/html", response["Content-Type"])

    def test_client_routes_return_the_shell(self):
        """A reload on /jobs must not 404; the router handles it client-side."""

        for route in ("/jobs", "/profile", "/cover/12", "/some/deep/route"):
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 200)
                self.assertIn("text/html", response["Content-Type"])

    def test_the_shell_is_never_cached(self):
        """It names hashed assets, so a stale copy would point at deleted files."""

        response = self.client.get("/jobs")
        self.assertIn("no-cache", response["Cache-Control"])

    def test_api_paths_are_not_caught_by_the_spa_fallback(self):
        """An unknown API route must 404, not hand back the SPA shell.

        Django's own 404 page is HTML, so the meaningful assertion is that this
        did *not* return the shell — otherwise a typo'd endpoint would answer
        200 with a working-looking page.
        """

        response = self.client.get("/api/definitely-not-a-route/")

        self.assertEqual(response.status_code, 404)
        self.assertNotIn(b'id="root"', self._body(response))

    def test_the_spa_does_not_shadow_the_admin(self):
        response = self.client.get("/admin/login/")
        self.assertNotEqual(response.status_code, 404)

    def test_slashless_admin_is_redirected_not_swallowed(self):
        """`/admin` must redirect to `/admin/`, not be answered by the SPA.

        The catch-all originally excluded `admin/` — with the slash. The bare
        `/admin` therefore matched the SPA view, so the URL *resolved*,
        `APPEND_SLASH` never fired, and the browser received an empty 200.
        Django's redirect only happens if nothing matches the URL.
        """

        response = self.client.get("/admin")

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], "/admin/")

    def test_other_slashless_prefixes_are_redirected_too(self):
        """The same trap applies to any URL Django would normally fix up.

        `/admin` is the one that bit us, because `admin/` is a real route and
        so `APPEND_SLASH` redirects it — but only if the catch-all does not
        match first.
        """

        response = self.client.get("/admin")

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], "/admin/")

    def test_a_route_merely_starting_with_a_reserved_word_is_still_served(self):
        """The exclusion must be a whole namespace, not a prefix or a word.

        `/administration` and `/static-assets` are client-side routes. An
        earlier version excluded on a bare prefix, and the one after that on a
        word boundary — which a hyphen satisfies, so `/static-assets` was
        wrongly withheld from the SPA.
        """

        for path in ("/administration", "/apiculture", "/static-assets", "/media-centre"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn("text/html", response["Content-Type"])

    def test_the_admin_redirect_is_relative(self):
        """An absolute redirect would leak the internal host to the browser.

        Behind the tunnel the origin is `127.0.0.1:8082`; the browser must be
        sent to `/admin/` on its own host, not to the loopback address.
        """

        with override_settings(ALLOWED_HOSTS=["sca.armin2080.de"]):
            response = self.client.get("/admin", HTTP_HOST="sca.armin2080.de")

        self.assertEqual(response["Location"], "/admin/")
        self.assertNotIn("127.0.0.1", response["Location"])

    def test_a_missing_build_is_reported_clearly(self):
        """Better an explicit error than a confusing 404 in production."""

        import config.urls as urls_module

        urls_module.SPA_ROOT = self.dist / "does-not-exist"
        response = self.client.get("/jobs")

        self.assertEqual(response.status_code, 404)


class MediaServingTests(TestCase):
    """Uploaded CVs must be downloadable in production.

    They were not. The route was registered with
    `django.conf.urls.static.static()`, which returns an empty list whenever
    DEBUG is false — so the obvious-looking line added no route at all and the
    files were unreachable. The tunnel only talks to gunicorn, so Django has to
    serve them.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._tmp = tempfile.TemporaryDirectory()
        cls.media = Path(cls._tmp.name)
        (cls.media / "cvs").mkdir()
        (cls.media / "cvs" / "example.pdf").write_bytes(b"%PDF-1.4 fake")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()
        super().tearDownClass()

    def setUp(self):
        self.override = override_settings(MEDIA_ROOT=self.media)
        self.override.enable()

    def tearDown(self):
        self.override.disable()

    def test_an_uploaded_file_is_served(self):
        response = self.client.get("/media/cvs/example.pdf")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"%PDF-1.4 fake")

    def test_a_missing_media_file_is_a_404_not_the_spa_shell(self):
        response = self.client.get("/media/cvs/nope.pdf")

        self.assertEqual(response.status_code, 404)

    def test_media_does_not_leak_outside_its_root(self):
        """Traversal must not reach the source tree."""

        response = self.client.get("/media/../manage.py")

        self.assertNotEqual(response.status_code, 200)
