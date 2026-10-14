"""Views for the cover letters domain."""

from __future__ import annotations

import logging

from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from config.serializers import EmptySerializer
from jobs.models import ActivityEntry, Job

from .models import CoverLetter
from .pdf import filename_for, render_pdf
from .serializers import (
    CoverLetterGenerateSerializer,
    CoverLetterPreviewSerializer,
    CoverLetterSerializer,
    CoverLetterUpdateSerializer,
)
from .services import CoverLetterError, generate

logger = logging.getLogger(__name__)


def _contact_lines(user) -> list[str]:
    profile = getattr(user, "profile", None)
    lines: list[str] = []
    if profile:
        if profile.portfolio:
            lines.append(profile.portfolio)
    if user.email:
        lines.append(user.email)
    if profile and profile.phone:
        lines.append(profile.phone)
    if profile and profile.location:
        lines.append(profile.location)
    return lines


def _cv_label(user) -> str:
    document = user.cv_documents.order_by("-uploaded_at").first()
    return document.file_name if document else "No CV uploaded"


class CoverLetterListCreateView(APIView):
    """GET /api/cover-letters/?job=<id> and POST /api/cover-letters/."""

    serializer_class = CoverLetterSerializer
    permission_classes = [IsAuthenticated]

    def get(self, request):
        job_param = request.query_params.get("job")

        if job_param is not None:
            try:
                job_id = int(job_param)
            except (TypeError, ValueError):
                return Response(
                    {"detail": "The `job` parameter must be an integer."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            letter = CoverLetter.objects.filter(user=request.user, job_id=job_id).first()
            if letter is None:
                # Explicit null so the client can distinguish "none yet".
                return Response(None)
            return Response(CoverLetterSerializer(letter).data)

        letters = CoverLetter.objects.filter(user=request.user).select_related("job")
        return Response(
            {
                "count": letters.count(),
                "next": None,
                "previous": None,
                "results": CoverLetterSerializer(letters, many=True).data,
            }
        )

    def post(self, request):
        serializer = CoverLetterGenerateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        job = Job.objects.filter(pk=data["jobId"], user=request.user).first()
        if job is None:
            return Response({"detail": "Job not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            content, generator = generate(
                user=request.user,
                job=job,
                language=data["language"],
                tone=data["tone"],
                length=data["length"],
                instructions=data.get("instructions", ""),
            )
        except CoverLetterError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        letter, _ = CoverLetter.objects.update_or_create(
            user=request.user,
            job=job,
            defaults={
                "content": content,
                "language": data["language"],
                "tone": data["tone"],
                "length": data["length"],
                "status": CoverLetter.Status.DRAFT,
                "generator": generator,
                "saved_at": None,
            },
        )

        if not job.has_cover_letter:
            job.has_cover_letter = True
            job.save(update_fields=["has_cover_letter", "updated_at"])

        ActivityEntry.objects.create(
            user=request.user,
            kind=ActivityEntry.Kind.COVER_LETTER,
            title="Cover letter generated",
            subtitle=job.company,
        )

        return Response(CoverLetterSerializer(letter).data, status=status.HTTP_201_CREATED)


class CoverLetterDetailView(APIView):
    """GET/PATCH /api/cover-letters/{id}/."""

    serializer_class = CoverLetterSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self, request, pk: int) -> CoverLetter | None:
        return CoverLetter.objects.filter(user=request.user, pk=pk).first()

    def get(self, request, pk: int):
        letter = self.get_object(request, pk)
        if letter is None:
            return Response({"detail": "Cover letter not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(CoverLetterSerializer(letter).data)

    def patch(self, request, pk: int):
        letter = self.get_object(request, pk)
        if letter is None:
            return Response({"detail": "Cover letter not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = CoverLetterUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        for field, value in serializer.validated_data.items():
            setattr(letter, field, value)

        letter.status = CoverLetter.Status.SAVED
        letter.saved_at = timezone.now()
        letter.save()

        return Response(CoverLetterSerializer(letter).data)


class CoverLetterRegenerateView(APIView):
    """POST /api/cover-letters/{id}/regenerate/."""

    serializer_class = CoverLetterSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request, pk: int):
        letter = CoverLetter.objects.filter(user=request.user, pk=pk).select_related("job").first()
        if letter is None:
            return Response({"detail": "Cover letter not found."}, status=status.HTTP_404_NOT_FOUND)

        data = request.data or {}
        language = data.get("language", letter.language)
        tone = data.get("tone", letter.tone)
        length = data.get("length", letter.length)
        instructions = data.get("instructions", "") or ""

        try:
            content, generator = generate(
                user=request.user,
                job=letter.job,
                language=language,
                tone=tone,
                length=length,
                instructions=instructions,
            )
        except CoverLetterError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        letter.content = content
        letter.language = language
        letter.tone = tone
        letter.length = length
        letter.generator = generator
        letter.status = CoverLetter.Status.DRAFT
        letter.saved_at = None
        letter.save()

        return Response(CoverLetterSerializer(letter).data)


class CoverLetterPdfView(APIView):
    """GET /api/cover-letters/{id}/pdf/ — returns raw PDF bytes."""

    serializer_class = EmptySerializer
    permission_classes = [IsAuthenticated]

    def get(self, request, pk: int):
        letter = CoverLetter.objects.filter(user=request.user, pk=pk).select_related("job").first()
        if letter is None:
            return Response({"detail": "Cover letter not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            payload = render_pdf(
                content=letter.content,
                company=letter.job.company,
                job_title=letter.job.title,
                candidate_name=request.user.full_name,
                contact_lines=_contact_lines(request.user),
            )
        except Exception:
            logger.exception("PDF rendering failed for cover letter %s", letter.pk)
            return Response(
                {"detail": "The PDF could not be generated."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        response = HttpResponse(payload, content_type="application/pdf")
        filename = filename_for(letter.job.company, letter.job.title)
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class CoverLetterPreviewView(APIView):
    """GET /api/cover-letters/preview/?job=<id> — context for the generation step."""

    serializer_class = CoverLetterPreviewSerializer
    permission_classes = [IsAuthenticated]

    def get(self, request):
        job_param = request.query_params.get("job")
        try:
            job_id = int(job_param)
        except (TypeError, ValueError):
            return Response(
                {"detail": "The `job` parameter must be an integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        job = Job.objects.filter(pk=job_id, user=request.user).first()
        if job is None:
            return Response({"detail": "Job not found."}, status=status.HTTP_404_NOT_FOUND)

        from jobs.serializers import JobSerializer

        return Response(
            {
                "jobId": job.id,
                "job": JobSerializer(job).data,
                "cvLabel": _cv_label(request.user),
                "language": "English",
                "tone": CoverLetter.Tone.PROFESSIONAL,
                "length": CoverLetter.Length.BALANCED,
            }
        )
