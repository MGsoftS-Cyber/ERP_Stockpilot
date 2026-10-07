# AI orchestration: tenant-authorized uploads and analysis requests are handled here.
# client.py calls FastAPI; models store extraction/recommendation results and human review state.
# Approved OCR creates a billing draft; recommendations remain advisory until a human acts.
"""AI orchestration: upload, extract, review and record advisory predictions."""

import hashlib
import json
import uuid
from datetime import timedelta

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit.services import record
from apps.billing.models import InvoiceLine
from apps.billing.services import create_invoice
from apps.catalog.models import Product
from apps.common.commands import (
    AI_ROLES,
    FINANCE_ROLES,
    Conflict,
    authorize,
    digest,
    lock_organization,
)
from apps.inventory.models import StockBalance, StockMovement, Warehouse

from .client import AIUnavailable, call_ai
from .models import OCRDocument, RecommendationRun


def upload_document(*, organization, actor, file):
    authorize(organization, actor, AI_ROLES)
    if file.size > 10 * 1024 * 1024:
        raise ValidationError("Upload at most 10 MiB.")
    raw = file.read(10 * 1024 * 1024 + 1)
    if len(raw) > 10 * 1024 * 1024 or not raw.startswith(
        (b"%PDF-", b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff")
    ):
        raise ValidationError("Choose a PNG, JPEG or PDF document of at most 10 MiB.")
    document = OCRDocument(
        organization=organization,
        created_by=actor,
        original_name=file.name[:240],
        sha256=hashlib.sha256(raw).hexdigest(),
    )
    try:
        with transaction.atomic():
            document.file.save("document.bin", ContentFile(raw), save=False)
            document.save()
            record(organization, actor, "ocr.uploaded", document, sha256=document.sha256)
    except Exception:
        # Database rollback cannot undo storage writes, so clean up this new file.
        if document.file:
            document.file.delete(save=False)
        raise
    return document


def extract(*, organization, actor, document_id):
    authorize(organization, actor, AI_ROLES)
    with transaction.atomic():
        document = (
            OCRDocument.objects.select_for_update()
            .filter(pk=document_id, organization=organization)
            .first()
        )
        if document is None:
            raise ValidationError("Document not found.")
        if document.status in ("REVIEW", "APPROVED"):
            return document
        # A timed-out worker lease is retryable after five minutes.
        if document.status == "PROCESSING" and document.updated_at > timezone.now() - timedelta(
            minutes=5
        ):
            raise Conflict("Extraction is already running.")
        document.status, document.attempt, document.error = "PROCESSING", uuid.uuid4(), ""
        document.save()
        attempt = document.attempt
    try:
        # Never hold database locks while waiting for OCR/native processes.
        with document.file.open("rb") as source:
            result = call_ai("ocr", raw=source.read())
        if not isinstance(result.get("fields"), dict) or not isinstance(
            result.get("raw_text"), str
        ):
            raise AIUnavailable()
    except (AIUnavailable, OSError) as error:
        with transaction.atomic():
            failed = OCRDocument.objects.select_for_update().get(pk=document_id)
            if failed.attempt == attempt:
                failed.status, failed.error = (
                    "FAILED",
                    "Extraction failed; check the service/document and retry.",
                )
                failed.save()
                record(organization, actor, "ocr.failed", failed)
        raise AIUnavailable() from error
    with transaction.atomic():
        document = OCRDocument.objects.select_for_update().get(pk=document_id)
        if document.attempt != attempt:
            raise Conflict("A newer extraction attempt replaced this result.")
        document.extraction, document.status = result, "REVIEW"
        document.save()
        record(
            organization, actor, "ocr.extracted", document, model_version=result["model_version"]
        )
    return document


@transaction.atomic
def approve_document(*, organization, actor, document_id, corrected):
    authorize(organization, actor, FINANCE_ROLES)
    lock_organization(organization)
    document = (
        OCRDocument.objects.select_for_update()
        .filter(pk=document_id, organization=organization)
        .first()
    )
    if document is None:
        raise ValidationError("Document not found.")
    # The service assigns kind and key. AI and the browser cannot choose POSTED status.
    corrected = {**corrected, "kind": "SUPPLIER", "idempotency_key": document.pk}
    approval_hash = digest(corrected)
    if document.status == "APPROVED":
        if document.approval_hash != approval_hash:
            raise Conflict("This document was already approved with different corrections.")
        return document
    if document.status != "REVIEW":
        raise Conflict("Extract the document and review the fields before approval.")
    invoice, _ = create_invoice(organization=organization, actor=actor, **corrected)
    if invoice.status != "DRAFT":
        raise Conflict("The document command key already belongs to a non-draft invoice.")
    document.invoice = invoice
    document.correction = json.loads(json.dumps(corrected, default=str))
    document.approval_hash, document.status = approval_hash, "APPROVED"
    document.save()
    record(organization, actor, "ocr.approved_draft", document, invoice_id=str(invoice.pk))
    return document


def run_forecast(*, organization, actor, product_id, warehouse_id, lead_time_days, horizon_days):
    authorize(organization, actor, AI_ROLES)
    if not 1 <= lead_time_days <= 90 or not 1 <= horizon_days <= 90:
        raise ValidationError("Lead time and horizon must be 1–90 days.")
    product = (
        Product.objects.select_related("unit")
        .filter(pk=product_id, organization=organization, is_active=True)
        .first()
    )
    warehouse = Warehouse.objects.filter(
        pk=warehouse_id, organization=organization, is_active=True
    ).first()
    if product is None or warehouse is None:
        raise ValidationError("Choose a product and warehouse in this organization.")
    # Exclude today's incomplete bucket. Missing days are real zero-shipment observations.
    today = timezone.localdate()
    start = today - timedelta(days=90)
    movements = (
        StockMovement.objects.filter(
            organization=organization,
            product=product,
            warehouse=warehouse,
            movement_type="SALE_SHIPMENT",
            occurred_at__date__gte=start,
            occurred_at__date__lt=today,
        )
        .annotate(day=TruncDate("occurred_at"))
        .values("day")
        .annotate(qty=Sum("quantity_signed"))
    )
    daily = {row["day"]: float(-row["qty"]) for row in movements}
    balance = StockBalance.objects.filter(
        organization=organization, product=product, warehouse=warehouse
    ).first()
    margins = (
        InvoiceLine.objects.filter(
            organization=organization,
            product=product,
            invoice__status="POSTED",
            invoice__kind="CUSTOMER",
            invoice__issued_on__gte=start,
            invoice__issued_on__lte=today,
        )
        .select_related("invoice")
        .order_by("-created_at")[:200]
    )
    inputs = dict(
        daily_demand=[daily.get(start + timedelta(days=i), 0) for i in range(90)],
        available=float(balance.on_hand - balance.reserved) if balance else 0,
        minimum_stock=float(product.minimum_stock),
        lead_time_days=lead_time_days,
        horizon_days=horizon_days,
        allows_decimals=product.unit.allows_decimals,
        margins=[
            dict(
                id=str(row.pk),
                revenue=float(row.net),
                cost=float(row.quantity * row.unit_cost),
                currency=row.invoice.currency,
            )
            for row in margins
        ],
    )
    with transaction.atomic():
        run = RecommendationRun.objects.create(
            organization=organization,
            created_by=actor,
            product=product,
            warehouse=warehouse,
            inputs={**inputs, "start_date": str(start), "end_date": str(today - timedelta(days=1))},
        )
        record(organization, actor, "forecast.started", run)
    try:
        result = call_ai("analyze", data=inputs)
        if "reorder_quantity" not in result or "mae" not in result:
            raise AIUnavailable()
    except AIUnavailable:
        with transaction.atomic():
            run.status, run.error = "FAILED", "Analysis unavailable; create a new run to retry."
            run.save()
            record(organization, actor, "forecast.failed", run)
        raise
    with transaction.atomic():
        run.status, run.result = "READY", result
        run.save()
        record(
            organization, actor, "forecast.completed", run, model_version=result["model_version"]
        )
    return run


@transaction.atomic
def decide(*, organization, actor, run_id, decision, note):
    authorize(organization, actor, AI_ROLES)
    run = (
        RecommendationRun.objects.select_for_update()
        .filter(pk=run_id, organization=organization)
        .first()
    )
    if run is None or run.status != "READY":
        raise Conflict("Only a completed recommendation can be reviewed.")
    if decision not in ("ACCEPTED", "REJECTED") or not note.strip():
        raise ValidationError("Accept/reject the recommendation and explain the decision.")
    if run.decision != "PENDING":
        if run.decision != decision or run.decision_note != note:
            raise Conflict("A recorded decision cannot be rewritten; create a new run.")
        return run
    run.decision, run.decision_note = decision, note
    run.decided_by, run.decided_at = actor, timezone.now()
    run.save()
    record(organization, actor, "forecast.decided", run, decision=decision, note=note)
    return run
