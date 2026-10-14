"""Uniform API error envelope.

Every error response is normalised to a shape the frontend understands:

    { "detail": "message", "errors": { "field": ["..."] } }

Validation failures keep their DRF field mapping under `errors`, so the client
can attach messages to the right inputs.
"""

import logging

from django.core.exceptions import PermissionDenied, ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)


def _flatten(detail) -> dict | list | str:
    if isinstance(detail, dict):
        return {key: _flatten(value) for key, value in detail.items()}
    if isinstance(detail, (list, tuple)):
        return [_flatten(item) for item in detail]
    return str(detail)


def api_exception_handler(exc, context):
    """Convert exceptions into a consistent `{detail, errors}` payload."""

    if isinstance(exc, DjangoValidationError):
        detail = _flatten(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)
        if isinstance(detail, dict):
            return Response({"detail": "Validation failed.", "errors": detail}, status=400)
        return Response({"detail": " ".join(detail) if isinstance(detail, list) else str(detail)}, status=400)

    if isinstance(exc, Http404):
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    if isinstance(exc, PermissionDenied):
        return Response({"detail": "You do not have permission to do that."}, status=status.HTTP_403_FORBIDDEN)

    response = drf_exception_handler(exc, context)

    if response is None:
        logger.exception("Unhandled API exception", exc_info=exc)
        return Response(
            {"detail": "Something went wrong on our side. Please try again shortly."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    data = response.data
    payload: dict

    if isinstance(data, dict) and "detail" in data and len(data) == 1:
        payload = {"detail": str(data["detail"])}
    elif isinstance(data, dict):
        payload = {"detail": "Validation failed.", "errors": _flatten(data)}
    elif isinstance(data, list):
        payload = {"detail": "Validation failed.", "errors": {"non_field_errors": _flatten(data)}}
    else:
        payload = {"detail": str(data)}

    response.data = payload
    return response
