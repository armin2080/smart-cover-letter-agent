"""LinkedIn adapter tests.

All fixtures are saved copies of the real markup shape. No test performs a live
request: the adapter's HTTP client is replaced with a stub.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from jobs.sources.base import EmploymentType, SearchRequest
from jobs.sources.linkedin import parser
from jobs.sources.linkedin.adapter import LinkedInAdapter

#: Mirrors the guest search-result markup: `li` cards containing
#: `.base-search-card` with a `data-entity-urn` and a full-link anchor.
SEARCH_FIXTURE = """
<html><body><ul>
  <li>
    <div class="base-card base-search-card job-search-card" data-entity-urn="urn:li:jobPosting:4420960628">
      <a class="base-card__full-link" href="https://de.linkedin.com/jobs/view/werkstudent-in-steuern-at-wepa-4420960628?position=1&amp;refId=abc&amp;trackingId=xyz"></a>
      <h3 class="base-search-card__title">Werkstudent/in Steuern (m/w/d)</h3>
      <h4 class="base-search-card__subtitle"><a href="/company/wepa">WEPA</a></h4>
      <span class="job-search-card__location">Müschede, Nordrhein-Westfalen, Deutschland</span>
      <time datetime="2026-10-09">Vor 3 Tagen</time>
    </div>
  </li>
  <li>
    <div class="base-card base-search-card job-search-card" data-entity-urn="urn:li:jobPosting:4475200717">
      <a class="base-card__full-link" href="https://de.linkedin.com/jobs/view/werkstudent-backend-at-startplatz-4475200717?refId=zzz"></a>
      <h3 class="base-search-card__title">Werkstudent Backend Entwicklung</h3>
      <h4 class="base-search-card__subtitle"><a href="/company/startplatz">STARTPLATZ</a></h4>
      <span class="job-search-card__location">Köln, Nordrhein-Westfalen, Deutschland</span>
    </div>
  </li>
  <li>
    <div class="base-card base-search-card job-search-card">
      <h3 class="base-search-card__title"></h3>
    </div>
  </li>
</ul></body></html>
"""

DETAIL_FIXTURE = """
<html><body>
  <div class="description__text">
    <span class="show-more-less-html__markup">
      Wir suchen einen Werkstudenten für Python- und Django-Entwicklung.
      <ul><li>Erfahrung mit SQL und Docker</li><li>Teamfähigkeit</li></ul>
    </span>
  </div>
  <span class="description__job-criteria-text">Working Student</span>
</body></html>
"""


class _StubResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code


class _StubClient:
    """Replaces the HTTP client so tests never touch the network."""

    def __init__(self, pages: dict[str, str]):
        self.pages = pages
        self.calls: list[tuple[str, dict]] = []

    def get(self, url: str, **kwargs):
        self.calls.append((url, kwargs))
        for fragment, body in self.pages.items():
            if fragment in url:
                return _StubResponse(body)
        return _StubResponse("")


class LinkedInParserTests(SimpleTestCase):
    def test_parses_title_company_location_and_id(self):
        jobs = parser.parse_search_page(SEARCH_FIXTURE)
        self.assertEqual(len(jobs), 2, "the empty card must be skipped")

        first = jobs[0]
        self.assertEqual(first.title, "Werkstudent/in Steuern (m/w/d)")
        self.assertEqual(first.company, "WEPA")
        self.assertEqual(first.location, "Müschede, Nordrhein-Westfalen, Deutschland")
        self.assertEqual(first.external_id, "4420960628")
        self.assertEqual(first.source, "LinkedIn")

    def test_strips_tracking_parameters(self):
        jobs = parser.parse_search_page(SEARCH_FIXTURE)
        for job in jobs:
            self.assertNotIn("?", job.url)
            self.assertNotIn("trackingId", job.url)

    def test_parses_posted_date(self):
        job = parser.parse_search_page(SEARCH_FIXTURE)[0]
        self.assertEqual(job.posted_at_raw, "2026-10-09")

    def test_empty_markup_yields_nothing(self):
        self.assertEqual(parser.parse_search_page(""), [])
        self.assertEqual(parser.parse_search_page("<html></html>"), [])

    def test_missing_optional_fields_are_tolerated(self):
        html = """
        <li><div class="base-search-card" data-entity-urn="urn:li:jobPosting:123456789">
          <h3 class="base-search-card__title">Werkstudent</h3>
        </div></li>
        """
        jobs = parser.parse_search_page(html)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].company, "")
        self.assertEqual(jobs[0].location, "")
        self.assertTrue(jobs[0].url)

    def test_detail_parsing(self):
        detail = parser.parse_job_detail(DETAIL_FIXTURE)
        self.assertIn("Werkstudenten", detail["description"])
        self.assertEqual(detail["employment_type_raw"], "Working Student")


class LinkedInAdapterTests(SimpleTestCase):
    def _adapter(self, pages: dict[str, str]) -> LinkedInAdapter:
        adapter = LinkedInAdapter.__new__(LinkedInAdapter)
        adapter.client = _StubClient(pages)
        return adapter

    def test_search_returns_normalized_records(self):
        adapter = self._adapter({"seeMoreJobPostings": SEARCH_FIXTURE})
        jobs = adapter.search(
            SearchRequest(keywords=["Werkstudent"], locations=["Dortmund"], max_results=10)
        )
        self.assertEqual(len(jobs), 2)
        self.assertTrue(all(job.source == "LinkedIn" for job in jobs))

    def test_search_deduplicates_across_pages(self):
        """The guest API re-serves postings; the adapter must not duplicate them."""

        adapter = self._adapter({"seeMoreJobPostings": SEARCH_FIXTURE})
        jobs = adapter.search(
            SearchRequest(keywords=["Werkstudent"], locations=["Dortmund"], max_results=50)
        )
        ids = [job.external_id for job in jobs]
        self.assertEqual(len(ids), len(set(ids)))

    def test_empty_result_set_is_handled(self):
        adapter = self._adapter({})
        jobs = adapter.search(SearchRequest(keywords=["nothing"], locations=["nowhere"]))
        self.assertEqual(jobs, [])

    def test_enrichment_adds_description(self):
        adapter = self._adapter({"jobPosting": DETAIL_FIXTURE})
        job = parser.parse_search_page(SEARCH_FIXTURE)[0]
        enriched = adapter.enrich(job)
        self.assertIn("Django", enriched.description)
        self.assertEqual(enriched.employment_type_raw, "Working Student")

    def test_enrichment_failure_leaves_record_intact(self):
        adapter = self._adapter({})
        job = parser.parse_search_page(SEARCH_FIXTURE)[0]
        original_title = job.title
        enriched = adapter.enrich(job)
        self.assertEqual(enriched.title, original_title)

    def test_normalize_applies_the_shared_classifier(self):
        adapter = self._adapter({})
        job = parser.parse_search_page(SEARCH_FIXTURE)[0]
        normalized = adapter.normalize(job)
        self.assertEqual(normalized.employment_type, EmploymentType.WORKING_STUDENT)
        self.assertEqual(normalized.city, "Müschede")
        self.assertEqual(normalized.region, "Nordrhein-Westfalen")
