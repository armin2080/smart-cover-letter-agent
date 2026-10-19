"""Views for the searches domain."""

from __future__ import annotations

from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AutoSearchSettings, SearchRun
from .runner import build_stages, start_search, summarise_criteria
from .serializers import AutoSearchSettingsSerializer, SearchCriteriaSerializer, SearchRunSerializer


class SearchRunListCreateView(APIView):
    """GET /api/searches/ (history) and POST /api/searches/ (start a search)."""

    serializer_class = SearchRunSerializer
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = SearchRun.objects.filter(user=request.user)

        try:
            page_size = min(int(request.query_params.get("page_size", 20)), 100)
        except (TypeError, ValueError):
            page_size = 20
        try:
            page = max(int(request.query_params.get("page", 1)), 1)
        except (TypeError, ValueError):
            page = 1

        total = queryset.count()
        start = (page - 1) * page_size
        items = queryset[start : start + page_size]

        return Response(
            {
                "count": total,
                "next": None,
                "previous": None,
                "results": SearchRunSerializer(items, many=True).data,
            }
        )

    def post(self, request):
        serializer = SearchCriteriaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        criteria = serializer.to_criteria()

        # Fill any gaps from the user's saved preferences.
        preferences = getattr(request.user, "preferences", None)
        if preferences is not None:
            if not criteria["roles"]:
                criteria["roles"] = list(preferences.desired_roles or [])
            if not criteria["locations"]:
                criteria["locations"] = list(preferences.locations or [])
            if not criteria["employment_types"]:
                criteria["employment_types"] = list(preferences.employment_types or [])
            if not criteria["keywords"]:
                criteria["keywords"] = list(preferences.keywords or [])
            if not criteria["language_filter"]:
                criteria["language_filter"] = preferences.language_filter or "any"
            if not criteria["sources"]:
                criteria["sources"] = list(preferences.sources or [])

        # A search must always be explicit about language, because the pipeline
        # reads the value directly and "" is not a preference.
        criteria["language_filter"] = criteria["language_filter"] or "any"

        sources = criteria["sources"] or ["LinkedIn", "StepStone", "Stellenwerk"]

        run = SearchRun.objects.create(
            user=request.user,
            mode=SearchRun.Mode.MANUAL,
            status=SearchRun.Status.QUEUED,
            started_at=timezone.now(),
            criteria=criteria,
            criteria_summary=summarise_criteria(criteria),
            sources=sources,
            stages=build_stages(),
        )

        start_search(run.id)
        run.refresh_from_db()
        return Response(SearchRunSerializer(run).data, status=status.HTTP_201_CREATED)


class SearchRunDetailView(APIView):
    """GET /api/searches/{id}/ — polled by the client during a run."""

    serializer_class = SearchRunSerializer
    permission_classes = [IsAuthenticated]

    def get(self, request, pk: int):
        run = SearchRun.objects.filter(user=request.user, pk=pk).first()
        if run is None:
            return Response({"detail": "Search run not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(SearchRunSerializer(run).data)


class SearchRunCancelView(APIView):
    """POST /api/searches/{id}/cancel/."""

    serializer_class = SearchRunSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request, pk: int):
        run = SearchRun.objects.filter(user=request.user, pk=pk).first()
        if run is None:
            return Response({"detail": "Search run not found."}, status=status.HTTP_404_NOT_FOUND)

        if not run.is_terminal:
            run.status = SearchRun.Status.FAILED
            run.error = "Search cancelled."
            run.finished_at = timezone.now()
            stages = list(run.stages or [])
            for index, stage in enumerate(stages):
                if stage.get("state") in {"active", "pending"}:
                    stages[index] = {**stage, "state": "error"}
            run.stages = stages
            run.save(update_fields=["status", "error", "finished_at", "stages"])

        return Response(SearchRunSerializer(run).data)


class AutoSearchSettingsView(APIView):
    """GET/PUT /api/searches/settings/."""

    serializer_class = AutoSearchSettingsSerializer
    permission_classes = [IsAuthenticated]

    def _settings(self, request) -> AutoSearchSettings:
        instance, created = AutoSearchSettings.objects.get_or_create(user=request.user)
        if created and not instance.sources:
            instance.sources = ["LinkedIn", "StepStone", "Stellenwerk"]
            instance.save()
        return instance

    def get(self, request):
        return Response(AutoSearchSettingsSerializer(self._settings(request)).data)

    def put(self, request):
        instance = self._settings(request)
        serializer = AutoSearchSettingsSerializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        instance.refresh_from_db()
        return Response(AutoSearchSettingsSerializer(instance).data)

    patch = put
