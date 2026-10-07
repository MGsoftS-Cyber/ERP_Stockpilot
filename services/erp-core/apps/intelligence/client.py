# Internal HTTP adapter: calls only fixed FastAPI OCR/analyze endpoints with a service token.
# It translates transport failures into an ERP service error without exposing credentials.
# intelligence/services.py controls permissions, private data and persistence around this call.
"""Only fixed internal endpoints are callable; users cannot supply a destination URL."""

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from rest_framework.exceptions import APIException


class AIUnavailable(APIException):
    status_code = 503
    default_detail = (
        "AI service is unavailable or could not process this input. Retry or review manually."
    )


def call_ai(endpoint, *, data=None, raw=None):
    if endpoint not in ("ocr", "analyze") or not settings.AI_SERVICE_TOKEN:
        raise AIUnavailable()
    payload = raw if raw is not None else json.dumps(data).encode()
    request = Request(
        f"{settings.AI_SERVICE_URL.rstrip('/')}/{endpoint}",
        data=payload,
        headers={
            "Content-Type": "application/octet-stream" if raw is not None else "application/json",
            "X-Service-Token": settings.AI_SERVICE_TOKEN,
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=180) as response:
            body = response.read(1_000_001)
        if len(body) > 1_000_000:
            raise ValueError("AI response exceeded limit")
        result = json.loads(body)
        if not isinstance(result, dict) or not result.get("model_version"):
            raise ValueError("Missing model version")
        return result
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
        raise AIUnavailable() from error
