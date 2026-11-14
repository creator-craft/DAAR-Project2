from typing import Any

from rest_framework.response import Response
from rest_framework.views import exception_handler as default_exception_handler


def first_message(detail: Any) -> str:
    if isinstance(detail, dict):
        field, value = next(iter(detail.items()))
        message = first_message(value)
        return (
            message
            if field in ("detail", "non_field_errors")
            else f"{field}: {message}"
        )
    if isinstance(detail, list):
        return first_message(detail[0]) if detail else "Invalid request."
    return str(detail)


def exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """Return every API error as `{"error": message}`, as expected by the frontend"""
    response = default_exception_handler(exc, context)
    if response is not None:
        response.data = {"error": first_message(response.data)}
    return response
