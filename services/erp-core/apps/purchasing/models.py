# Model database records, relationships and constraints.
from django.db import models
from django.db.models import F, Q

from apps.common.models import OrganizationScopedModel


class PurchaseOrder(OrganizationScopedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SUBMITTED = "SUBMITTED", "Submitted"
        APPROVED = "APPROVED", "Approved"
        PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED", "Partially received"
        RECEIVED = "RECEIVED", "Received"
        CLOSED = "CLOSED", "Closed"
        CANCELLED = "CANCELLED", "Cancelled"
    reference = models.CharField(max_length=64)
    supplier = models.ForeignKey("partners.BusinessPartner", on_delete=models.PROTECT)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.DRAFT)
    notes = models.TextField(blank=True)
    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "reference"], name="po_reference_per_org"
            )
        ]


class PurchaseOrderLine(OrganizationScopedModel):
    order = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name="lines")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    received_quantity = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    unit_price = models.DecimalField(max_digits=18, decimal_places=4)
    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["order", "product"], name="po_unique_product"),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="po_positive_qty"),
            models.CheckConstraint(condition=Q(unit_price__gte=0), name="po_nonnegative_price"),
            models.CheckConstraint(
                condition=Q(received_quantity__gte=0) & Q(received_quantity__lte=F("quantity")),
                name="po_received_within_ordered",
            ),
        ]


class GoodsReceipt(OrganizationScopedModel):
    order = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name="receipts")
    warehouse = models.ForeignKey("inventory.Warehouse", on_delete=models.PROTECT)
    idempotency_key = models.UUIDField()
    payload_hash = models.CharField(max_length=64)
    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "idempotency_key"], name="receipt_key_per_org"
            )
        ]


class GoodsReceiptLine(OrganizationScopedModel):
    receipt = models.ForeignKey(GoodsReceipt, on_delete=models.PROTECT, related_name="lines")
    order_line = models.ForeignKey(PurchaseOrderLine, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["receipt", "order_line"], name="receipt_unique_line"),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="receipt_positive_qty"),
        ]


class PurchaseEvent(OrganizationScopedModel):
    """Service-written purchasing history; no writable API or admin is exposed."""
    order = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name="events")
    action = models.CharField(max_length=32)
    detail = models.TextField(blank=True)
    class Meta:
        ordering = ["created_at", "id"]
