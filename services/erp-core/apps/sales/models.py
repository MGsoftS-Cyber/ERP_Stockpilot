"""Sales records: orders promise goods; shipments record actual delivery."""

from django.db import models
from django.db.models import F, Q

from apps.common.models import OrganizationScopedModel


class SalesOrder(OrganizationScopedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        CONFIRMED = "CONFIRMED", "Confirmed"
        PARTIALLY_SHIPPED = "PARTIALLY_SHIPPED", "Partially shipped"
        SHIPPED = "SHIPPED", "Shipped"
        CANCELLED = "CANCELLED", "Cancelled remainder"

    # Each order fulfils from one warehouse; split orders for multiple warehouses.
    reference = models.CharField(max_length=64)
    customer = models.ForeignKey("partners.BusinessPartner", on_delete=models.PROTECT)
    warehouse = models.ForeignKey("inventory.Warehouse", on_delete=models.PROTECT)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.DRAFT)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "reference"], name="sales_reference"),
        ]


class SalesOrderLine(OrganizationScopedModel):
    order = models.ForeignKey(SalesOrder, on_delete=models.PROTECT, related_name="lines")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    unit_price = models.DecimalField(max_digits=18, decimal_places=4)
    # Cost is captured when confirming, independently of the customer's selling price.
    unit_cost = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    shipped_quantity = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    reservation = models.OneToOneField(
        "inventory.StockReservation", on_delete=models.PROTECT, null=True, blank=True
    )

    class Meta:
        ordering = ["product_id"]
        constraints = [
            models.UniqueConstraint(fields=["order", "product"], name="sales_product_once"),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="sales_quantity_positive"),
            models.CheckConstraint(condition=Q(unit_price__gte=0), name="sales_price_nonnegative"),
            models.CheckConstraint(condition=Q(unit_cost__gte=0), name="sales_cost_nonnegative"),
            models.CheckConstraint(
                condition=Q(shipped_quantity__gte=0, shipped_quantity__lte=F("quantity")),
                name="sales_shipped_bounds",
            ),
        ]


class Shipment(OrganizationScopedModel):
    order = models.ForeignKey(SalesOrder, on_delete=models.PROTECT, related_name="shipments")
    # This key identifies the logical command, not each retry of the HTTP request.
    idempotency_key = models.UUIDField()
    payload_hash = models.CharField(max_length=64)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "idempotency_key"], name="shipment_command_once"
            ),
        ]


class ShipmentLine(OrganizationScopedModel):
    shipment = models.ForeignKey(Shipment, on_delete=models.PROTECT, related_name="lines")
    order_line = models.ForeignKey(SalesOrderLine, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    returned_quantity = models.DecimalField(max_digits=18, decimal_places=4, default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["shipment", "order_line"], name="shipment_line_once"),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="shipment_quantity_positive"),
            models.CheckConstraint(
                condition=Q(returned_quantity__gte=0, returned_quantity__lte=F("quantity")),
                name="shipment_return_bounds",
            ),
        ]


class CustomerReturn(OrganizationScopedModel):
    # Returns reference delivered quantities, never just an arbitrary product ID.
    shipment = models.ForeignKey(Shipment, on_delete=models.PROTECT, related_name="returns")
    reason = models.TextField()
    idempotency_key = models.UUIDField()
    payload_hash = models.CharField(max_length=64)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "idempotency_key"], name="return_command_once"
            ),
        ]


class CustomerReturnLine(OrganizationScopedModel):
    customer_return = models.ForeignKey(
        CustomerReturn, on_delete=models.PROTECT, related_name="lines"
    )
    shipment_line = models.ForeignKey(ShipmentLine, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=18, decimal_places=4)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["customer_return", "shipment_line"], name="return_line_once"
            ),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="return_quantity_positive"),
        ]


class SalesEvent(OrganizationScopedModel):
    # Business history is read-only through the API and Django admin.
    order = models.ForeignKey(SalesOrder, on_delete=models.PROTECT, related_name="events")
    action = models.CharField(max_length=32)
    detail = models.TextField(blank=True)

    class Meta:
        ordering = ["created_at", "id"]
