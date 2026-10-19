"""Views for the jobs domain."""

from __future__ import annotations

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from config.serializers import CountsSerializer

from .models import ActivityEntry, Job, job_fingerprint
from .serializers import (
    ActivityEntrySerializer,
    JobDetailSerializer,
    JobSerializer,
    JobStatsSerializer,
    JobStatusUpdateSerializer,
    ManualJobImportSerializer,
    ProviderStatusSerializer,
)

ORDERING_MAP = {
    "newest": ("-posted_at", "-id"),
    "oldest": ("posted_at", "id"),
    "match": ("match", "-posted_at"),
}

# "strong" < "good" < "potential" alphabetically, which matches the intended
# ordering for the "match" sort: strongest first.
MATCH_RANK = {"strong": 0, "good": 1, "potential": 2}


def user_jobs(user):
    return Job.objects.filter(user=user)


class JobListView(APIView):
    """GET /api/jobs/ — the user's jobs with filtering, search and ordering."""

    serializer_class = JobSerializer
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = user_jobs(request.user)

        job_status = request.query_params.get("status")
        if job_status:
            queryset = queryset.filter(status=job_status)

        source = request.query_params.get("source")
        if source:
            queryset = queryset.filter(source__iexact=source)

        location = request.query_params.get("location")
        if location:
            queryset = queryset.filter(location__icontains=location)

        employment_type = request.query_params.get("employment_type")
        if employment_type:
            queryset = queryset.filter(employment_type=employment_type)

        # The language tabs. "Any" must not filter at all: postings whose
        # language could not be determined still belong in the full list.
        language = request.query_params.get("language")
        if language and language != "any":
            queryset = queryset.filter(language=language)

        match = request.query_params.get("match")
        if match:
            queryset = queryset.filter(match=match)

        company = request.query_params.get("company")
        if company:
            queryset = queryset.filter(company__icontains=company)

        query = request.query_params.get("q")
        if query:
            queryset = queryset.filter(
                Q(title__icontains=query) | Q(company__icontains=query) | Q(location__icontains=query)
            )

        ordering = ORDERING_MAP.get(request.query_params.get("ordering", "newest"), ORDERING_MAP["newest"])
        results = list(queryset.order_by(*ordering))

        if ordering[0] == "match":
            results.sort(key=lambda job: (MATCH_RANK.get(job.match, 9), -job.posted_at.timestamp()))

        page = self.paginate(results, request)
        serializer = JobSerializer(page["items"], many=True)
        return Response(
            {
                "count": page["count"],
                "next": page["next"],
                "previous": page["previous"],
                "results": serializer.data,
            }
        )

    @staticmethod
    def paginate(items: list, request) -> dict:
        """Slice the result list according to `page` / `page_size`."""

        try:
            page_size = min(int(request.query_params.get("page_size", 50)), 200)
        except (TypeError, ValueError):
            page_size = 50
        try:
            page_number = max(int(request.query_params.get("page", 1)), 1)
        except (TypeError, ValueError):
            page_number = 1

        total = len(items)
        start = (page_number - 1) * page_size
        end = start + page_size

        def build_url(number: int | None) -> str | None:
            if number is None:
                return None
            params = request.query_params.copy()
            params["page"] = number
            return f"{request.build_absolute_uri(request.path)}?{params.urlencode()}"

        next_url = build_url(page_number + 1) if end < total else None
        previous_url = build_url(page_number - 1) if page_number > 1 else None

        return {
            "items": items[start:end],
            "count": total,
            "next": next_url,
            "previous": previous_url,
        }


class JobCountsView(APIView):
    """GET /api/jobs/counts/ — status tallies used by the My Jobs tabs."""

    serializer_class = CountsSerializer
    permission_classes = [IsAuthenticated]

    def get(self, request):
        counts = {
            row["status"]: row["total"]
            for row in user_jobs(request.user).values("status").annotate(total=Count("id"))
        }
        languages = {
            row["language"]: row["total"]
            for row in user_jobs(request.user).values("language").annotate(total=Count("id"))
        }
        return Response(
            {
                "new": counts.get(Job.Status.NEW, 0),
                "reviewed": counts.get(Job.Status.REVIEWED, 0),
                "saved": counts.get(Job.Status.SAVED, 0),
                "dismissed": counts.get(Job.Status.DISMISSED, 0),
                # Tallies for the language tabs. `any` is the total rather than
                # the sum of the others, because "unknown" belongs to the full
                # list but has no tab of its own.
                "languages": {
                    "any": sum(languages.values()),
                    "german": languages.get("german", 0),
                    "english": languages.get("english", 0),
                    "unknown": languages.get("unknown", 0),
                },
            }
        )


class JobDetailView(APIView):
    """GET/PATCH /api/jobs/{id}/."""

    serializer_class = JobDetailSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self, request, pk: int) -> Job | None:
        return user_jobs(request.user).filter(pk=pk).first()

    def get(self, request, pk: int):
        job = self.get_object(request, pk)
        if job is None:
            return Response({"detail": "Job not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(JobDetailSerializer(job).data)

    def patch(self, request, pk: int):
        job = self.get_object(request, pk)
        if job is None:
            return Response({"detail": "Job not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = JobStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data["status"]

        previous = job.status
        if new_status != previous:
            job.status = new_status
            job.save(update_fields=["status", "updated_at"])
            self._log_activity(request, job, new_status)

        return Response(JobSerializer(job).data)

    @staticmethod
    def _log_activity(request, job: Job, new_status: str) -> None:
        kind_map = {
            Job.Status.SAVED: ActivityEntry.Kind.SAVED,
            Job.Status.REVIEWED: ActivityEntry.Kind.REVIEWED,
            Job.Status.DISMISSED: ActivityEntry.Kind.DISMISSED,
        }
        kind = kind_map.get(new_status)
        if kind is None:
            return
        ActivityEntry.objects.create(
            user=request.user,
            kind=kind,
            title=f"{job.title} marked as {new_status}",
            subtitle=job.company,
        )


class JobStatsView(APIView):
    """GET /api/jobs/stats/ — dashboard summary cards plus search schedule."""

    serializer_class = JobStatsSerializer
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from searches.models import AutoSearchSettings  # local import avoids a circular import

        jobs = user_jobs(request.user)
        counts = {
            row["status"]: row["total"] for row in jobs.values("status").annotate(total=Count("id"))
        }
        cover_letters = request.user.cover_letters.count()

        cards = [
            {
                "key": "new",
                "label": "New matches",
                "value": counts.get(Job.Status.NEW, 0),
                "hint": "Ready to review",
            },
            {
                "key": "reviewed",
                "label": "Reviewed jobs",
                "value": counts.get(Job.Status.REVIEWED, 0),
                "hint": "Looked at recently",
            },
            {
                "key": "saved",
                "label": "Saved jobs",
                "value": counts.get(Job.Status.SAVED, 0),
                "hint": "Worth revisiting",
            },
            {
                "key": "cover-letters",
                "label": "Cover letters",
                "value": cover_letters,
                "hint": "Drafted or saved",
            },
        ]

        auto, _ = AutoSearchSettings.objects.get_or_create(user=request.user)

        payload = {
            "cards": cards,
            "automaticSearchActive": auto.enabled,
            "lastSearchAt": auto.last_run_at,
            "nextSearchAt": auto.next_run_at if auto.enabled else None,
            # Reported separately so the UI can distinguish "scheduled and
            # will run" from "scheduled, but nothing is set up to run it".
            "schedulerActive": settings.AUTO_SEARCH_SCHEDULER_ENABLED,
        }
        return Response(JobStatsSerializer(payload).data)


class JobRecentView(APIView):
    """GET /api/jobs/recent/?limit=5 — latest non-dismissed matches."""

    serializer_class = JobSerializer
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            limit = min(max(int(request.query_params.get("limit", 5)), 1), 50)
        except (TypeError, ValueError):
            limit = 5

        jobs = user_jobs(request.user).exclude(status=Job.Status.DISMISSED).order_by("-posted_at")[:limit]
        return Response(JobSerializer(jobs, many=True).data)


class ActivityListView(APIView):
    """GET /api/activity/?limit=8 — recent activity feed."""

    serializer_class = ActivityEntrySerializer
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            limit = min(max(int(request.query_params.get("limit", 8)), 1), 100)
        except (TypeError, ValueError):
            limit = 8

        entries = ActivityEntry.objects.filter(user=request.user)[:limit]
        return Response(ActivityEntrySerializer(entries, many=True).data)


# --------------------------------------------------------------------------- #
# Provider status and manual import                                           #
# --------------------------------------------------------------------------- #


class ProviderStatusView(APIView):
    """GET /api/jobs/providers/ — which sources may actually be used.

    Reports the authorization state per platform so the UI can be honest about
    what is and is not connected. A provider without written authorization is
    reported as disabled rather than as working.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = ProviderStatusSerializer

    def get(self, request):
        from jobs.sources.registry import PROVIDERS, provider_health

        health = {entry.source: entry for entry in provider_health()}

        payload = []
        for name, config in PROVIDERS.items():
            entry = health.get(name)
            status = entry.status if entry else None
            payload.append(
                {
                    "source": name,
                    "displayName": config.display_name,
                    "status": status.value if status else "unknown",
                    "statusLabel": status.label if status else "Unknown",
                    "operational": bool(status and status.is_operational),
                    "detail": entry.detail if entry else "",
                    "termsNote": config.terms_note,
                }
            )

        return Response(ProviderStatusSerializer(payload, many=True).data)


class ManualJobImportView(APIView):
    """POST /api/jobs/import/ — add a listing the user supplies themselves.

    This is the path that works without any platform authorization, because it
    performs no third-party automated access. The supplied URL is stored for the
    user to visit but is never fetched by the server.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = ManualJobImportSerializer

    def post(self, request):
        serializer = ManualJobImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        from jobs.matching import build_insight
        from jobs.sources.manual.adapter import build_manual_job
        from jobs.sources.normalization import normalize_raw_job

        raw = build_manual_job(
            url=data.get("url", ""),
            title=data["title"],
            company=data.get("company", ""),
            location=data.get("location", ""),
            employment_type=data.get("employmentType", ""),
            description=data.get("description", ""),
            notes=data.get("notes", ""),
        )
        job = normalize_raw_job(raw)

        # A manual entry has no stable external id, so the fingerprint falls back
        # to the user-supplied fields.
        fingerprint = job_fingerprint(
            "Manual", job.source_url, job.title, job.company
        )
        if Job.objects.filter(user=request.user, fingerprint=fingerprint).exists():
            return Response(
                {
                    "detail": "You have already added this job.",
                    "errors": {"title": ["This job is already in your list."]},
                },
                status=status.HTTP_409_CONFLICT,
            )

        insight = _insight_for(request.user, job)

        created = Job.objects.create(
            user=request.user,
            title=job.title[:255],
            company=job.company[:255],
            location=job.location[:255],
            city=job.city[:120],
            region=job.region[:120],
            country=job.country[:80],
            employment_type=job.employment_type.value,
            employment_type_confidence=job.employment_type_confidence,
            employment_type_evidence=job.employment_type_evidence,
            work_model=job.work_model.value,
            summary=(job.description[:400] if job.description else ""),
            description=job.description,
            skills=job.required_skills,
            source="Manual",
            source_url=job.source_url[:1024],
            is_user_provided=True,
            provenance=[
                {"source": "Manual", "url": job.source_url, "external_id": "", "user_provided": True}
            ],
            raw_source_data=job.raw_source_data,
            posted_at=job.posted_at or timezone.now(),
            collected_at=job.collected_at or timezone.now(),
            match=insight.match,
            cv_alignment=insight.cv_dicts,
            preference_fit=insight.preference_dicts,
            status=Job.Status.NEW,
            fingerprint=fingerprint,
        )

        return Response(JobDetailSerializer(created).data, status=status.HTTP_201_CREATED)


def _insight_for(user, job):
    """Run the matching engine for a single normalized job."""

    from jobs.matching import build_insight

    profile = getattr(user, "profile", None)
    preferences = getattr(user, "preferences", None)
    sections = {section.key: section.content for section in user.profile_sections.all()}

    return build_insight(
        job_title=job.title,
        company=job.company,
        location=job.location,
        employment_type=job.employment_type.value,
        source=job.source,
        job_skills=job.required_skills,
        job_requirements=[],
        job_summary=job.description,
        desired_roles=list(getattr(preferences, "desired_roles", []) or []),
        preferred_locations=list(getattr(preferences, "locations", []) or []),
        employment_types=list(getattr(preferences, "employment_types", []) or []),
        preferred_sources=list(getattr(preferences, "sources", []) or []),
        keywords=list(getattr(preferences, "keywords", []) or []),
        profile_sections=sections,
        profile_summary=getattr(profile, "summary", "") or "",
        radius_km=getattr(preferences, "radius_km", None),
    )


# --------------------------------------------------------------------------- #
# Independent job actions                                                     #
# --------------------------------------------------------------------------- #


class _JobActionView(APIView):
    """Base class for the independent review/save/dismiss actions.

    The actions are deliberately independent: saving does not clear "reviewed",
    and dismissing preserves the fact that a job was saved. Only the denormalised
    `status` is recomputed.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = JobSerializer

    #: Which timestamp this action sets, and whether it toggles.
    field: str = ""
    toggles: bool = False
    activity_kind: str = ""

    def post(self, request, pk: int):
        job = user_jobs(request.user).filter(pk=pk).first()
        if job is None:
            return Response({"detail": "Job not found."}, status=status.HTTP_404_NOT_FOUND)

        currently_set = getattr(job, self.field) is not None
        if self.toggles and currently_set:
            setattr(job, self.field, None)
            # Undo a dismissal or save by clearing it; other timestamps remain.
            if self.field == "dismissed_at":
                job.saved_at = None
        else:
            setattr(job, self.field, timezone.now())

        job.sync_status()
        job.save(update_fields=[self.field, "status", "updated_at"])

        if self.activity_kind and not (self.toggles and currently_set):
            ActivityEntry.objects.create(
                user=request.user,
                kind=self.activity_kind,
                title=f"{job.title} marked as {job.status}",
                subtitle=job.company,
            )

        return Response(JobSerializer(job).data)


class JobReviewView(_JobActionView):
    """POST /api/jobs/{id}/review/"""

    field = "reviewed_at"
    activity_kind = ActivityEntry.Kind.REVIEWED


class JobSaveView(_JobActionView):
    """POST /api/jobs/{id}/save/ — toggles."""

    field = "saved_at"
    toggles = True
    activity_kind = ActivityEntry.Kind.SAVED


class JobDismissView(_JobActionView):
    """POST /api/jobs/{id}/dismiss/"""

    field = "dismissed_at"
    activity_kind = ActivityEntry.Kind.DISMISSED


class JobRestoreView(APIView):
    """POST /api/jobs/{id}/restore/ — clear every interaction timestamp."""

    permission_classes = [IsAuthenticated]
    serializer_class = JobSerializer

    def post(self, request, pk: int):
        job = user_jobs(request.user).filter(pk=pk).first()
        if job is None:
            return Response({"detail": "Job not found."}, status=status.HTTP_404_NOT_FOUND)

        job.reviewed_at = None
        job.saved_at = None
        job.dismissed_at = None
        job.sync_status()
        job.save(update_fields=["reviewed_at", "saved_at", "dismissed_at", "status", "updated_at"])
        return Response(JobSerializer(job).data)
