"""Persist AI evidence in Django; the stateless AI service never owns ERP data."""

from django.db import models

from apps.common.models import OrganizationScopedModel


def private_document_path(instance, filename):
    # The supplied filename cannot control directories or expose another tenant's file.
    return f"ocr/{instance.organization_id}/{instance.pk}/document.bin"


class OCRDocument(OrganizationScopedModel):
    file = models.FileField(upload_to=private_document_path)
    original_name = models.CharField(max_length=240)
    sha256 = models.CharField(max_length=64)
    status = models.CharField(
        max_length=16,
        default="UPLOADED",
        choices=[
            (s, s.title()) for s in ["UPLOADED", "PROCESSING", "REVIEW", "FAILED", "APPROVED"]
        ],
    )
    extraction = models.JSONField(default=dict)
    correction = models.JSONField(default=dict)
    error = models.CharField(max_length=240, blank=True)
    attempt = models.UUIDField(null=True)
    # A resulting invoice always starts as DRAFT; posting is a separate finance action.
    invoice = models.OneToOneField("billing.Invoice", on_delete=models.PROTECT, null=True)
    approval_hash = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ["-created_at"]


class RecommendationRun(OrganizationScopedModel):
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT)
    warehouse = models.ForeignKey("inventory.Warehouse", on_delete=models.PROTECT)
    inputs = models.JSONField()
    result = models.JSONField(default=dict)
    status = models.CharField(max_length=16, default="RUNNING")
    error = models.CharField(max_length=240, blank=True)
    # A decision records a review; acceptance does not create purchase orders.
    decision = models.CharField(
        max_length=16,
        default="PENDING",
        choices=[(s, s.title()) for s in ["PENDING", "ACCEPTED", "REJECTED"]],
    )
    decision_note = models.TextField(blank=True)
    decided_by = models.ForeignKey(
        "tenancy.User", on_delete=models.PROTECT, null=True, related_name="ai_decisions"
    )
    decided_at = models.DateTimeField(null=True)

    class Meta:
        ordering = ["-created_at"]
