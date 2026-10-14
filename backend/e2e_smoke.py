"""End-to-end smoke test against the real HTTP API with live providers.

Run from `backend/` with the project virtualenv:

    .venv/bin/python e2e_smoke.py

Exercises the full path a browser would take: register, complete a profile, run
a search against the live adapters, then read the resulting job list and the
provider status panel. Deleted afterwards — this is a manual verification
script, not part of the suite.
"""

from __future__ import annotations

import os
import sys
import time

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.test import Client  # noqa: E402  (must follow django.setup)
from rest_framework_simplejwt.tokens import RefreshToken  # noqa: E402

from django.contrib.auth import get_user_model  # noqa: E402

User = get_user_model()

EMAIL = "e2e-live-test@example.com"
PASSWORD = "e2e-test-pass-9931"

ok = 0
failed = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global ok, failed
    ok += condition
    failed += not condition
    print(f"  [{'PASS' if condition else 'FAIL'}] {label}{(' — ' + detail) if detail else ''}")


def main() -> int:
    User.objects.filter(email=EMAIL).delete()
    user = User.objects.create_user(email=EMAIL, password=PASSWORD)
    client = Client()
    token = str(RefreshToken.for_user(user).access_token)
    client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {token}"

    print("\n=== 1. Provider status ===")
    resp = client.get("/api/jobs/providers/")
    check("GET /api/jobs/providers/ -> 200", resp.status_code == 200, str(resp.status_code))
    providers = resp.json()
    for entry in providers:
        print(f"        {entry['source']:13} {entry['status']:32} operational={entry['operational']}")
    live = [p for p in providers if p["source"] != "manual"]
    check("platform providers report as operational", all(p["operational"] for p in live))

    print("\n=== 2. Profile ===")
    profile = {
        "fullName": "E2E Tester",
        "headline": "Werkstudent Softwareentwicklung",
        "location": "Dortmund",
        "skills": ["Python", "Django", "TypeScript", "React", "SQL"],
        "experience": "Werkstudent Backend Developer bei Kleiner GmbH, 2024 - heute",
        "education": "B.Sc. Informatik, TU Dortmund",
    }
    resp = client.patch("/api/profile/", profile, content_type="application/json")
    check("PATCH /api/profile/ -> 2xx", 200 <= resp.status_code < 300, str(resp.status_code))

    print("\n=== 3. Start a search (live sources) ===")
    payload = {
        "keywords": ["Werkstudent Softwareentwicklung"],
        "locations": ["Dortmund"],
        "sources": ["linkedin", "stepstone", "stellenwerk"],
        "employmentTypes": ["working-student", "student-assistant", "internship"],
        "maxResults": 30,
    }
    started = time.time()
    resp = client.post("/api/searches/", payload, content_type="application/json")
    check("POST /api/searches/ -> 2xx", 200 <= resp.status_code < 300, str(resp.status_code))
    if not (200 <= resp.status_code < 300):
        print("        body:", resp.content[:900])
        return 1

    run = resp.json()
    run_id = run.get("id")
    print(f"        run id={run_id} status={run.get('status')}")

    print("\n=== 4. Poll to completion ===")
    terminal = {"completed", "failed", "partial"}
    for _ in range(60):
        resp = client.get(f"/api/searches/{run_id}/")
        run = resp.json()
        if run.get("status") in terminal:
            break
        time.sleep(1)
    print(f"        status={run.get('status')} after {time.time() - started:.1f}s")
    check("run reached a terminal state", run.get("status") in terminal, str(run.get("status")))

    print("\n=== 5. Stage progress ===")
    for stage in run.get("stages", []):
        print(f"        {stage.get('label', stage.get('key')):34} {stage.get('state'):10} {stage.get('detail', '')}")
    failed_stages = [s for s in run.get("stages", []) if s.get("state") == "failed"]
    check("no stage failed", not failed_stages, str([s.get("key") for s in failed_stages]))

    print("\n=== 6. Source outcomes / warnings ===")
    for note in run.get("warnings", []) or ["(none)"]:
        print(f"        ! {note}")
    print(f"        found={run.get('found')} matched={run.get('matched')}")

    print("\n=== 7. Resulting jobs ===")
    resp = client.get("/api/jobs/?ordering=-created")
    check("GET /api/jobs/ -> 200", resp.status_code == 200, str(resp.status_code))
    body = resp.json()
    jobs = body.get("results", body) if isinstance(body, dict) else body
    print(f"        {len(jobs)} job(s) in the list")
    for job in jobs[:12]:
        print(f"        - {job.get('title', '')[:46]:48} {job.get('company', '')[:24]:26} "
              f"{job.get('match', ''):>9} {job.get('employmentType', '')}")

    check("at least one job was persisted", len(jobs) > 0)
    tiers = {j.get("match") for j in jobs}
    check("match verdicts are populated", bool(tiers - {None, ""}), str(sorted(t for t in tiers if t)))
    check("verdicts are a known set", tiers <= {"strong", "good", "potential"}, str(sorted(t for t in tiers if t)))
    strong = sum(1 for j in jobs if j.get("match") == "strong")
    print(f"        strong={strong} good={sum(1 for j in jobs if j.get('match') == 'good')} "
          f"potential={sum(1 for j in jobs if j.get('match') == 'potential')}")

    print(f"\n=== RESULT: {ok} passed, {failed} failed ===")
    User.objects.filter(email=EMAIL).delete()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
