# Inventory model: immutable movements record quantity changes; balances project current totals.
# Reservation records distinguish promised quantities from stock physically on hand.
# Model constraints support services; business commands, not CRUD forms, control posting.
# Teaching edition: Model database records, relationships and constraints.
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.common.models import (
    OrganizationScopedModel,
    OrganizationScopedQuerySet,
)


class Warehouse(OrganizationScopedModel):
    # Text field: max_length limits length; choices supplies permitted values.
    code = models.CharField(max_length=40)
    # Text field: max_length limits length; choices supplies permitted values.
    name = models.CharField(max_length=120)
    # Long text; validate its business meaning in the input/service contract.
    address = models.TextField(blank=True)
    # True/False flag; default is used when creating without a value.
    is_active = models.BooleanField(default=True)

    # Django metadata: schema or API options, not a constructor.
    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "code"],
                name="unique_warehouse_code_per_organization",
            )
        ]

    # Return a readable label for admin and debugging without modifying data.
    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class StockAdjustment(OrganizationScopedModel):
    # Text field: max_length limits length; choices supplies permitted values.
    reference = models.CharField(max_length=64)
    # Many records refer to one parent; on_delete controls deletion behavior.
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="stock_adjustments",
    )
    # Long text; validate its business meaning in the input/service contract.
    reason = models.TextField()
    # Stable identifier; UUIDs do not replace permission checks.
    idempotency_key = models.UUIDField()
    # Timestamp; automatic dates run during applicable model saves.
    posted_at = models.DateTimeField(default=timezone.now)

    # Django metadata: schema or API options, not a constructor.
    class Meta:
        ordering = ["-posted_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "reference"],
                name="unique_adjustment_reference_per_organization",
            ),
            models.UniqueConstraint(
                fields=["organization", "idempotency_key"],
                name="unique_adjustment_idempotency_per_organization",
            ),
        ]

    # Return a readable label for admin and debugging without modifying data.
    def __str__(self) -> str:
        return self.reference


class StockAdjustmentLine(OrganizationScopedModel):
    # Many records refer to one parent; on_delete controls deletion behavior.
    adjustment = models.ForeignKey(
        StockAdjustment,
        on_delete=models.PROTECT,
        related_name="lines",
    )
    # Many records refer to one parent; on_delete controls deletion behavior.
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.PROTECT,
        related_name="stock_adjustment_lines",
    )
    # Exact decimal value; max_digits includes integer and fractional digits.
    quantity_signed = models.DecimalField(max_digits=18, decimal_places=4)
    # Exact decimal value; max_digits includes integer and fractional digits.
    unit_cost = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal("0.0000"),
        validators=[MinValueValidator(Decimal("0"))],
    )

    # Django metadata: schema or API options, not a constructor.
    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["adjustment", "product"],
                name="one_adjustment_line_per_product",
            ),
            models.CheckConstraint(
                condition=~Q(quantity_signed=0),
                name="adjustment_quantity_is_not_zero",
            ),
            models.CheckConstraint(
                condition=Q(unit_cost__gte=0),
                name="adjustment_unit_cost_not_negative",
            ),
        ]


class StockTransfer(OrganizationScopedModel):
    # Text field: max_length limits length; choices supplies permitted values.
    reference = models.CharField(max_length=64)
    # Many records refer to one parent; on_delete controls deletion behavior.
    source_warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="outgoing_stock_transfers",
    )
    # Many records refer to one parent; on_delete controls deletion behavior.
    destination_warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="incoming_stock_transfers",
    )
    # Long text; validate its business meaning in the input/service contract.
    reason = models.TextField(blank=True)
    # Stable identifier; UUIDs do not replace permission checks.
    idempotency_key = models.UUIDField()
    # Timestamp; automatic dates run during applicable model saves.
    transferred_at = models.DateTimeField(default=timezone.now)

    # Django metadata: schema or API options, not a constructor.
    class Meta:
        ordering = ["-transferred_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "reference"],
                name="unique_transfer_reference_per_organization",
            ),
            models.UniqueConstraint(
                fields=["organization", "idempotency_key"],
                name="unique_transfer_idempotency_per_organization",
            ),
            models.CheckConstraint(
                condition=~Q(source_warehouse=F("destination_warehouse")),
                name="transfer_warehouses_are_different",
            ),
        ]

    # Return a readable label for admin and debugging without modifying data.
    def __str__(self) -> str:
        return self.reference


class StockTransferLine(OrganizationScopedModel):
    # Many records refer to one parent; on_delete controls deletion behavior.
    transfer = models.ForeignKey(
        StockTransfer,
        on_delete=models.PROTECT,
        related_name="lines",
    )
    # Many records refer to one parent; on_delete controls deletion behavior.
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.PROTECT,
        related_name="stock_transfer_lines",
    )
    # Exact decimal value; max_digits includes integer and fractional digits.
    quantity = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.0001"))],
    )
    # Exact decimal value; max_digits includes integer and fractional digits.
    unit_cost = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal("0.0000"),
        validators=[MinValueValidator(Decimal("0"))],
    )

    # Django metadata: schema or API options, not a constructor.
    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["transfer", "product"],
                name="one_transfer_line_per_product",
            ),
            models.CheckConstraint(
                condition=Q(quantity__gt=0),
                name="transfer_quantity_is_positive",
            ),
            models.CheckConstraint(
                condition=Q(unit_cost__gte=0),
                name="transfer_unit_cost_not_negative",
            ),
        ]


class ImmutableStockMovementQuerySet(OrganizationScopedQuerySet):
    # Guard bulk writes so queryset updates cannot rewrite ledger history.
    def update(self, **kwargs):
        raise ValidationError("Posted stock movements are immutable.")

    # Protect immutable history instead of silently removing earlier events.
    def delete(self):
        raise ValidationError("Posted stock movements are immutable.")


class StockMovement(OrganizationScopedModel):
    class MovementType(models.TextChoices):
        OPENING = "OPENING", "Opening balance"
        PURCHASE_RECEIPT = "PURCHASE_RECEIPT", "Purchase receipt"
        SALE_SHIPMENT = "SALE_SHIPMENT", "Sale shipment"
        CUSTOMER_RETURN = "CUSTOMER_RETURN", "Customer return"
        SUPPLIER_RETURN = "SUPPLIER_RETURN", "Supplier return"
        ADJUSTMENT_IN = "ADJUSTMENT_IN", "Adjustment in"
        ADJUSTMENT_OUT = "ADJUSTMENT_OUT", "Adjustment out"
        TRANSFER_IN = "TRANSFER_IN", "Transfer in"
        TRANSFER_OUT = "TRANSFER_OUT", "Transfer out"

    class SourceType(models.TextChoices):
        STOCK_ADJUSTMENT = "STOCK_ADJUSTMENT", "Stock adjustment"
        STOCK_TRANSFER = "STOCK_TRANSFER", "Stock transfer"
        PURCHASE_RECEIPT = "PURCHASE_RECEIPT", "Purchase receipt"
        SHIPMENT = "SHIPMENT", "Shipment"
        CUSTOMER_RETURN = "CUSTOMER_RETURN", "Customer return"
        SUPPLIER_RETURN = "SUPPLIER_RETURN", "Supplier return"

    # Many records refer to one parent; on_delete controls deletion behavior.
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.PROTECT,
        related_name="stock_movements",
    )
    # Many records refer to one parent; on_delete controls deletion behavior.
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="stock_movements",
    )
    # Text field: max_length limits length; choices supplies permitted values.
    movement_type = models.CharField(max_length=32, choices=MovementType.choices)
    # Exact decimal value; max_digits includes integer and fractional digits.
    quantity_signed = models.DecimalField(max_digits=18, decimal_places=4)
    # Exact decimal value; max_digits includes integer and fractional digits.
    unit_cost = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal("0.0000"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    # Timestamp; automatic dates run during applicable model saves.
    occurred_at = models.DateTimeField(default=timezone.now)
    # Text field: max_length limits length; choices supplies permitted values.
    source_type = models.CharField(max_length=32, choices=SourceType.choices)
    # Stable identifier; UUIDs do not replace permission checks.
    source_id = models.UUIDField()
    # Stable identifier; UUIDs do not replace permission checks.
    idempotency_key = models.UUIDField(unique=True)

    objects = ImmutableStockMovementQuerySet.as_manager()

    # Django metadata: schema or API options, not a constructor.
    class Meta:
        ordering = ["-occurred_at", "-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=~Q(quantity_signed=0),
                name="stock_movement_quantity_is_not_zero",
            ),
            models.CheckConstraint(
                condition=Q(unit_cost__gte=0),
                name="movement_unit_cost_not_negative",
            ),
        ]
        indexes = [
            models.Index(
                fields=["organization", "product", "warehouse", "occurred_at"],
                name="movement_stock_history_idx",
            ),
            models.Index(
                fields=["organization", "source_type", "source_id"],
                name="movement_source_idx",
            ),
        ]

    # Guard record writes here; business posting still belongs in services.
    def save(self, *args, **kwargs) -> None:
        if not self._state.adding:
            raise ValidationError("Posted stock movements are immutable.")
        super().save(*args, **kwargs)

    # Protect immutable history instead of silently removing earlier events.
    def delete(self, *args, **kwargs):
        raise ValidationError("Posted stock movements are immutable.")


class StockBalance(OrganizationScopedModel):
    # Many records refer to one parent; on_delete controls deletion behavior.
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.PROTECT,
        related_name="stock_balances",
    )
    # Many records refer to one parent; on_delete controls deletion behavior.
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="stock_balances",
    )
    # Exact decimal value; max_digits includes integer and fractional digits.
    on_hand = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))
    # Exact decimal value; max_digits includes integer and fractional digits.
    reserved = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))

    # Django metadata: schema or API options, not a constructor.
    class Meta:
        ordering = ["product__name", "warehouse__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "product", "warehouse"],
                name="unique_product_warehouse_balance",
            ),
            models.CheckConstraint(
                condition=Q(on_hand__gte=0),
                name="stock_balance_on_hand_is_not_negative",
            ),
            models.CheckConstraint(
                condition=Q(reserved__gte=0),
                name="stock_balance_reserved_is_not_negative",
            ),
            models.CheckConstraint(
                condition=Q(reserved__lte=F("on_hand")),
                name="stock_balance_reserved_not_above_on_hand",
            ),
        ]

    @property
    def available(self) -> Decimal:
        return self.on_hand - self.reserved

    @property
    def is_low_stock(self) -> bool:
        return self.available <= self.product.minimum_stock


class StockReservation(OrganizationScopedModel):
    class SourceType(models.TextChoices):
        MANUAL = "MANUAL", "Manual"
        SALES_ORDER = "SALES_ORDER", "Sales order"
        OTHER = "OTHER", "Other"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        RELEASED = "RELEASED", "Released"
        FULFILLED = "FULFILLED", "Fulfilled"

    # Many records refer to one parent; on_delete controls deletion behavior.
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.PROTECT,
        related_name="stock_reservations",
    )
    # Many records refer to one parent; on_delete controls deletion behavior.
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="stock_reservations",
    )
    # Exact decimal value; max_digits includes integer and fractional digits.
    quantity = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.0001"))],
    )
    # Text field: max_length limits length; choices supplies permitted values.
    source_type = models.CharField(max_length=32, choices=SourceType.choices)
    # Stable identifier; UUIDs do not replace permission checks.
    source_id = models.UUIDField()
    # Text field: max_length limits length; choices supplies permitted values.
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    # Stable identifier; UUIDs do not replace permission checks.
    idempotency_key = models.UUIDField()
    # Timestamp; automatic dates run during applicable model saves.
    released_at = models.DateTimeField(null=True, blank=True)
    # Preserve original reserved quantity; consumption tracks partial shipments.
    # Exact decimal value; max_digits includes integer and fractional digits.
    fulfilled_quantity = models.DecimalField(max_digits=18, decimal_places=4, default=0)

    # Django metadata: schema or API options, not a constructor.
    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "idempotency_key"],
                name="unique_reservation_idempotency_per_organization",
            ),
            models.CheckConstraint(
                condition=Q(quantity__gt=0),
                name="reservation_quantity_is_positive",
            ),
            models.CheckConstraint(
                condition=Q(fulfilled_quantity__gte=0, fulfilled_quantity__lte=F("quantity")),
                name="reservation_fulfilled_bounds",
            ),
        ]
