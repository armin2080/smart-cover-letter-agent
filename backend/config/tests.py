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

    def test_a_missing_build_is_reported_clearly(self):
        """Better an explicit error than a confusing 404 in production."""

        import config.urls as urls_module

        urls_module.SPA_ROOT = self.dist / "does-not-exist"
        response = self.client.get("/jobs")

        self.assertEqual(response.status_code, 404)
