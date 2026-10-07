# Teaching edition: Return consistent client errors without internal tracebacks.
from rest_framework.response import Response
from rest_framework.views import exception_handler


def stockpilot_exception_handler(exc: Exception, context: dict) -> Response | None:
    """Return one predictable error envelope for React and future gateway clients."""

    response = exception_handler(exc, context)
    if response is None:
        return None

    detail = response.data
    response.data = {
        "error": {
            "status": response.status_code,
            "code": getattr(exc, "default_code", "api_error"),
            "detail": detail,
        }
    }
    return response
