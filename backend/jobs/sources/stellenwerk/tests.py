"""Stellenwerk adapter tests.

Stellenwerk is a SvelteKit app whose city pages are server-rendered. Fixtures
mirror the real card structure. No test performs a live request.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from jobs.sources.base import EmploymentType, SearchRequest
from jobs.sources.stellenwerk import parser
from jobs.sources.stellenwerk.adapter import StellenwerkAdapter

CITY_FIXTURE = """
<html><body>
  <a href="/dortmund/werkstudent-mwd-softwareentwicklung-261012-277527" class="flex flex-col">
    <div class="flex items-start gap-3">
      <p class="min-w-0 flex-1 text-lg text-primary sm:text-xl font-bold">Werkstudent (m/w/d) - Softwareentwicklung</p>
      <p class="text-base text-gray-700 sm:text-lg">LogProIT GmbH &middot; Dortmund, Deutschland</p>
      <span class="inline-flex items-center rounded-full px-3 py-1">Werkstudentenstelle</span>
      <p class="relative flex items-center text-sm text-gray">vor 5 Stunden</p>
    </div>
  </a>
  <a href="/dortmund/traineeprogramm-bauingenieurwesen-wmd-261013-278251" class="flex flex-col">
    <div>
      <p class="min-w-0 flex-1 text-lg font-bold">Traineeprogramm Bauingenieurwesen (w/m/d)</p>
      <p class="text-base text-gray-700 sm:text-lg">Autobahn GmbH &middot; Deutschland</p>
      <span class="inline-flex items-center rounded-full px-3 py-1">Absolvent:innenjob</span>
      <p class="relative flex items-center text-sm text-gray">vor 2 Tagen</p>
    </div>
  </a>
  <a href="/faq">FAQ</a>
  <a href="/dortmund/events">Events</a>
</body></html>
"""

DETAIL_FIXTURE = """
<html><body>
  <nav><p>Folge uns auf Insta</p><p>Für Studenten</p></nav>
  <header><p>Jobs Veranstaltungen Karriereservice Magazin</p></header>
  <main><div class="flex flex-grow flex-col"><div class="mx-auto flex max-w-screen-xl">
    <div class="flex w-full flex-col gap-4">
      <p>Als innovatives IT-Unternehmen aus Dortmund entwickeln wir Softwarelösungen
      und suchen Verstärkung im Bereich Python und Django. Wir arbeiten mit Docker
      und PostgreSQL.</p>
      <ul><li>Erfahrung mit Python</li><li>Teamfähigkeit</li></ul>
    </div>
  </div></div></main>
  <footer><p>Impressum Datenschutz</p></footer>
</body></html>
"""


class _StubResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code


class _StubClient:
    def __init__(self, pages: dict[str, str]):
        self.pages = pages
        self.calls: list[tuple[str, dict]] = []

    def get(self, url: str, **kwargs):
        self.calls.append((url, kwargs))
        for fragment, body in self.pages.items():
            if fragment in url:
                return _StubResponse(body)
        return _StubResponse("")


class StellenwerkParserTests(SimpleTestCase):
    def test_resolves_city_slugs(self):
        self.assertEqual(parser.resolve_city("Dortmund"), "dortmund")
        self.assertEqual(parser.resolve_city("München"), "muenchen")
        self.assertEqual(parser.resolve_city("Munich"), "muenchen")
        self.assertEqual(parser.resolve_city("Köln"), "koeln")
        self.assertEqual(parser.resolve_city("Cologne"), "koeln")

    def test_an_umlaut_city_resolves_to_its_slug(self):
        """Regression: "Düsseldorf" matched nothing and became Dortmund.

        `KNOWN_CITIES` holds the ASCII slug "duesseldorf", so the umlaut had to
        be folded first. Without that a user adding Düsseldorf to their
        locations was silently shown Dortmund jobs instead.
        """

        self.assertEqual(parser.resolve_city("Düsseldorf"), "duesseldorf")
        self.assertEqual(parser.resolve_city("Dusseldorf"), "duesseldorf")
        self.assertEqual(parser.resolve_city("düsseldorf"), "duesseldorf")

    def test_unknown_city_resolves_to_nothing(self):
        """Returning another city would misreport where the jobs are.

        A default is not a safe failure here: the result looks identical to a
        genuine match on the requested city.
        """

        self.assertIsNone(parser.resolve_city("Nowhereville"))
        self.assertIsNone(parser.resolve_city(""))

    def test_parses_job_cards_only(self):
        jobs = parser.parse_city_page(CITY_FIXTURE, city="dortmund")
        self.assertEqual(len(jobs), 2, "navigation links must be ignored")

    def test_parses_title_company_location(self):
        job = parser.parse_city_page(CITY_FIXTURE, city="dortmund")[0]
        self.assertEqual(job.title, "Werkstudent (m/w/d) - Softwareentwicklung")
        self.assertEqual(job.company, "LogProIT GmbH")
        self.assertEqual(job.location, "Dortmund, Deutschland")
        self.assertEqual(job.source, "Stellenwerk")
        self.assertTrue(job.url.startswith("https://www.stellenwerk.de/dortmund/"))

    def test_captures_badge_as_employment_hint(self):
        job = parser.parse_city_page(CITY_FIXTURE, city="dortmund")[0]
        self.assertEqual(job.employment_type_raw, "Werkstudentenstelle")

    def test_parses_relative_date(self):
        job = parser.parse_city_page(CITY_FIXTURE, city="dortmund")[0]
        self.assertEqual(job.posted_at_raw, "vor 5 Stunden")

    def test_empty_page(self):
        self.assertEqual(parser.parse_city_page("", city="dortmund"), [])

    def test_detail_excludes_page_chrome(self):
        """The description must come from the content block, not the nav."""

        detail = parser.parse_job_detail(DETAIL_FIXTURE)
        description = detail["description"]
        self.assertIn("IT-Unternehmen", description)
        self.assertNotIn("Folge uns auf Insta", description)
        self.assertNotIn("Impressum", description)

    def test_detail_handles_empty_page(self):
        self.assertEqual(parser.parse_job_detail(""), {})


class StellenwerkAdapterTests(SimpleTestCase):
    def _adapter(self, pages: dict[str, str]) -> StellenwerkAdapter:
        adapter = StellenwerkAdapter.__new__(StellenwerkAdapter)
        adapter.client = _StubClient(pages)
        return adapter

    def test_search_parses_city_page(self):
        adapter = self._adapter({"stellenwerk.de": CITY_FIXTURE})
        jobs = adapter.search(SearchRequest(keywords=["Werkstudent"], locations=["Dortmund"]))
        self.assertEqual(len(jobs), 2)

    def test_search_requests_the_resolved_city(self):
        adapter = self._adapter({"stellenwerk.de": CITY_FIXTURE})
        adapter.search(SearchRequest(keywords=["x"], locations=["München"]))
        url = adapter.client.calls[0][0]
        self.assertIn("/muenchen", url)

    def test_search_respects_max_results(self):
        adapter = self._adapter({"stellenwerk.de": CITY_FIXTURE})
        jobs = adapter.search(SearchRequest(keywords=["x"], locations=["Dortmund"], max_results=1))
        self.assertEqual(len(jobs), 1)

    def test_every_location_is_requested(self):
        """Regression: only `locations[0]` was ever fetched.

        Adding a second city to the preferences changed nothing, and there was
        no sign of it in the result — the same silent no-op as only passing
        the first keyword.
        """

        adapter = self._adapter({"stellenwerk.de": CITY_FIXTURE})
        adapter.search(
            SearchRequest(keywords=["x"], locations=["Dortmund", "Düsseldorf"], max_results=10)
        )

        requested = [url for url, _ in adapter.client.calls]
        self.assertTrue(any("/dortmund" in url for url in requested), requested)
        self.assertTrue(any("/duesseldorf" in url for url in requested), requested)

    def test_an_uncovered_location_does_not_borrow_another_city(self):
        """Jobs from a city the user never asked for must not be returned."""

        adapter = self._adapter({"stellenwerk.de": CITY_FIXTURE})
        jobs = adapter.search(
            SearchRequest(keywords=["x"], locations=["Nowhereville", "Dortmund"], max_results=10)
        )

        requested = [url for url, _ in adapter.client.calls]
        self.assertTrue(all("/dortmund" in url for url in requested), requested)
        self.assertEqual(len(jobs), 2)

    def test_enrichment_adds_description(self):
        adapter = self._adapter({"dortmund/werkstudent": DETAIL_FIXTURE})
        job = parser.parse_city_page(CITY_FIXTURE, city="dortmund")[0]
        enriched = adapter.enrich(job)
        self.assertIn("Django", enriched.description)

    def test_enrichment_failure_is_tolerated(self):
        adapter = self._adapter({})
        job = parser.parse_city_page(CITY_FIXTURE, city="dortmund")[0]
        self.assertEqual(adapter.enrich(job).title, job.title)

    def test_normalize_classifies_employment_type(self):
        adapter = self._adapter({})
        job = parser.parse_city_page(CITY_FIXTURE, city="dortmund")[0]
        normalized = adapter.normalize(job)
        self.assertEqual(normalized.employment_type, EmploymentType.WORKING_STUDENT)
        self.assertEqual(normalized.city, "Dortmund, Deutschland".split(",")[0])

    def test_second_card_classified_as_other(self):
        adapter = self._adapter({})
        job = parser.parse_city_page(CITY_FIXTURE, city="dortmund")[1]
        normalized = adapter.normalize(job)
        # "Absolvent:innenjob" is a graduate role, not a working-student post.
        self.assertNotEqual(normalized.employment_type, EmploymentType.WORKING_STUDENT)
