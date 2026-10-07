# Teaching edition: Model database records, relationships and constraints.
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

    # Text field: max_length limits length; choices supplies permitted values.
    reference = models.CharField(max_length=64)
    # Many records refer to one parent; on_delete controls deletion behavior.
    supplier = models.ForeignKey("partners.BusinessPartner", on_delete=models.PROTECT)
    # Text field: max_length limits length; choices supplies permitted values.
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.DRAFT)
    # Long text; validate its business meaning in the input/service contract.
    notes = models.TextField(blank=True)

    # Django metadata: schema or API options, not a constructor.
    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "reference"], name="po_reference_per_org"
            )
        ]


class PurchaseOrderLine(OrganizationScopedModel):
    # Many records refer to one parent; on_delete controls deletion behavior.
    order = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name="lines")
    # Many records refer to one parent; on_delete controls deletion behavior.
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT)
    # Exact decimal value; max_digits includes integer and fractional digits.
    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    # Exact decimal value; max_digits includes integer and fractional digits.
    received_quantity = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    # Exact decimal value; max_digits includes integer and fractional digits.
    unit_price = models.DecimalField(max_digits=18, decimal_places=4)

    # Django metadata: schema or API options, not a constructor.
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
    # Many records refer to one parent; on_delete controls deletion behavior.
    order = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name="receipts")
    # Many records refer to one parent; on_delete controls deletion behavior.
    warehouse = models.ForeignKey("inventory.Warehouse", on_delete=models.PROTECT)
    # Stable identifier; UUIDs do not replace permission checks.
    idempotency_key = models.UUIDField()
    # Text field: max_length limits length; choices supplies permitted values.
    payload_hash = models.CharField(max_length=64)

    # Django metadata: schema or API options, not a constructor.
    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "idempotency_key"], name="receipt_key_per_org"
            )
        ]


class GoodsReceiptLine(OrganizationScopedModel):
    # Many records refer to one parent; on_delete controls deletion behavior.
    receipt = models.ForeignKey(GoodsReceipt, on_delete=models.PROTECT, related_name="lines")
    # Many records refer to one parent; on_delete controls deletion behavior.
    order_line = models.ForeignKey(PurchaseOrderLine, on_delete=models.PROTECT)
    # Exact decimal value; max_digits includes integer and fractional digits.
    quantity = models.DecimalField(max_digits=18, decimal_places=4)

    # Django metadata: schema or API options, not a constructor.
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["receipt", "order_line"], name="receipt_unique_line"),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="receipt_positive_qty"),
        ]


class PurchaseEvent(OrganizationScopedModel):
    """Service-written purchasing history; no writable API or admin is exposed."""

    # Many records refer to one parent; on_delete controls deletion behavior.
    order = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name="events")
    # Text field: max_length limits length; choices supplies permitted values.
    action = models.CharField(max_length=32)
    # Long text; validate its business meaning in the input/service contract.
    detail = models.TextField(blank=True)

    # Django metadata: schema or API options, not a constructor.
    class Meta:
        ordering = ["created_at", "id"]
