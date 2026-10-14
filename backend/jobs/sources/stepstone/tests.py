"""StepStone adapter tests.

StepStone returns structured JSON, so these fixtures mirror the documented
`items` / `pagination` shape rather than HTML. No test performs a live request.
"""

from __future__ import annotations

import json

from django.test import SimpleTestCase

from jobs.sources.base import EmploymentType, SearchRequest
from jobs.sources.stepstone import parser
from jobs.sources.stepstone.adapter import StepStoneAdapter

RESULT_FIXTURE = {
    "items": [
        {
            "id": 14588073,
            "title": "Werkstudent Softwareentwicklung Java (m/w/d)",
            "url": "/stellenangebote--Werkstudent-Softwareentwicklung-Java-Berlin-Atruvia-AG--14588073-inline.html",
            "companyName": "Atruvia AG",
            "location": "Berlin",
            "textSnippet": "Python, SQL und Docker im Team.",
            "datePosted": "2026-10-09T00:00:00Z",
        },
        {
            "id": 14588075,
            "title": "Praktikum Data Science",
            "url": "/stellenangebote--Praktikum-Data-Science-München--14588075-inline.html",
            "companyName": "Cobalt Analytics",
            "location": "München",
            "textSnippet": "Pandas und Tableau.",
            "datePosted": "2026-10-08T00:00:00Z",
        },
        {
            "id": 0,
            "title": "",
            "url": "/stellenangebote--empty--0-inline.html",
            "companyName": "Ignored",
            "location": "",
            "textSnippet": "",
            "datePosted": "",
        },
    ],
    "pagination": {"page": 1, "perPage": 25, "pageCount": 2, "totalCount": 3},
}

EMPTY_FIXTURE = {"items": [], "pagination": {"page": 1, "perPage": 25, "pageCount": 0, "totalCount": 0}}


class _StubResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code


class _StubClient:
    def __init__(self, payloads: list[str]):
        self.payloads = payloads
        self.calls: list[tuple[str, dict]] = []

    def post(self, url: str, **kwargs):
        self.calls.append((url, kwargs))
        if not self.payloads:
            return _StubResponse(json.dumps(EMPTY_FIXTURE))
        return _StubResponse(self.payloads.pop(0))


class StepStoneParserTests(SimpleTestCase):
    def test_parses_items(self):
        jobs, pagination = parser.parse_result_list(RESULT_FIXTURE)
        self.assertEqual(len(jobs), 2, "the empty item must be skipped")

        first = jobs[0]
        self.assertEqual(first.title, "Werkstudent Softwareentwicklung Java (m/w/d)")
        self.assertEqual(first.company, "Atruvia AG")
        self.assertEqual(first.location, "Berlin")
        self.assertEqual(first.external_id, "14588073")
        self.assertEqual(first.source, "StepStone")
        self.assertTrue(first.url.startswith("https://www.stepstone.de/"))

    def test_pagination_is_read(self):
        _, pagination = parser.parse_result_list(RESULT_FIXTURE)
        self.assertEqual(parser.total_pages(pagination), 2)

    def test_json_string_payload(self):
        jobs, _ = parser.parse_result_list(json.dumps(RESULT_FIXTURE))
        self.assertEqual(len(jobs), 2)

    def test_malformed_json_is_handled(self):
        jobs, pagination = parser.parse_result_list("not json at all")
        self.assertEqual(jobs, [])
        self.assertEqual(pagination, {})

    def test_empty_result_set(self):
        jobs, _ = parser.parse_result_list(EMPTY_FIXTURE)
        self.assertEqual(jobs, [])

    def test_absolute_urls_are_preserved(self):
        payload = {
            "items": [
                {
                    "id": 1,
                    "title": "Werkstudent",
                    "url": "https://www.stepstone.de/stellenangebote--x--1-inline.html",
                    "companyName": "Acme",
                    "location": "Berlin",
                }
            ]
        }
        jobs, _ = parser.parse_result_list(payload)
        self.assertEqual(jobs[0].url, "https://www.stepstone.de/stellenangebote--x--1-inline.html")

    def test_request_body_shape(self):
        body = parser.build_request_body("/work/x/in-y", session_id="abc")
        self.assertEqual(body["lang"], "en")
        self.assertEqual(body["siteId"], parser.SITE_ID)
        self.assertEqual(body["fields"], ["items", "pagination"])
        self.assertEqual(body["userData"]["userHashId"], "abc")

    def test_session_id_is_stable_not_rotated(self):
        """Rotating the session id would be an evasion technique."""

        first = parser.build_request_body("/x", session_id="fixed")
        second = parser.build_request_body("/x", session_id="fixed")
        self.assertEqual(first["userData"]["userHashId"], second["userData"]["userHashId"])


class StepStoneAdapterTests(SimpleTestCase):
    def _adapter(self, payloads: list[dict]) -> StepStoneAdapter:
        adapter = StepStoneAdapter.__new__(StepStoneAdapter)
        adapter.client = _StubClient([json.dumps(payload) for payload in payloads])
        adapter.session_id = "test-session"
        return adapter

    def test_search_parses_and_deduplicates(self):
        adapter = self._adapter([RESULT_FIXTURE, EMPTY_FIXTURE])
        jobs = adapter.search(
            SearchRequest(keywords=["Werkstudent"], locations=["Berlin"], max_results=10)
        )
        self.assertEqual(len(jobs), 2)
        ids = [job.external_id for job in jobs]
        self.assertEqual(len(ids), len(set(ids)))

    def test_search_stops_on_empty_page(self):
        adapter = self._adapter([EMPTY_FIXTURE])
        jobs = adapter.search(SearchRequest(keywords=["x"], locations=["y"]))
        self.assertEqual(jobs, [])

    def test_search_respects_max_results(self):
        adapter = self._adapter([RESULT_FIXTURE, EMPTY_FIXTURE])
        jobs = adapter.search(
            SearchRequest(keywords=["x"], locations=["y"], max_results=1)
        )
        self.assertEqual(len(jobs), 1)

    def test_normalize_classifies_employment_type(self):
        adapter = self._adapter([RESULT_FIXTURE])
        job = parser.parse_result_list(RESULT_FIXTURE)[0][0]
        normalized = adapter.normalize(job)
        self.assertEqual(normalized.employment_type, EmploymentType.WORKING_STUDENT)
        self.assertIn("Python", normalized.required_skills)
        self.assertEqual(normalized.city, "Berlin")
