# Internal FastAPI boundary: authenticates service-to-service calls from Django.
# OCR/forecast modules return analysis results; they have no ERP database credentials.
# Django owns tenant access, persistence and the human approval workflow.
"""Internal AI API: no database credentials, no stock or invoice mutation routes."""

import hmac
import os

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from .forecast import ForecastInput, analyze
from .ocr import extract_document

app = FastAPI(title="StockPilot AI", version="0.8.0")


def authenticate(x_service_token: str = Header(default="")):
    expected = os.getenv("AI_SERVICE_TOKEN", "")
    if not expected or not hmac.compare_digest(x_service_token, expected):
        raise HTTPException(status_code=401, detail="Service authentication required.")


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.8.0"}


@app.post("/ocr", dependencies=[Depends(authenticate)])
async def ocr(request: Request):
    # Enforce the limit while reading, including chunked requests without Content-Length.
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 10 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Document exceeds 10 MiB.")
    try:
        return await run_in_threadpool(extract_document, bytes(raw))
    except Exception as error:
        # Do not leak native process stderr, filesystem paths or uploaded text.
        raise HTTPException(
            status_code=422,
            detail="Could not read document. Use a clear PNG/JPEG or unencrypted PDF of 1–5 pages.",
        ) from error


@app.post("/analyze", dependencies=[Depends(authenticate)])
def forecast(data: ForecastInput):
    try:
        return analyze(data)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
