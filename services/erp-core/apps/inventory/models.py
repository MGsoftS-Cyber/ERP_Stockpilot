# Model database records, relationships and constraints.
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
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=120)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
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
    reference = models.CharField(max_length=64)
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="stock_adjustments",
    )
    reason = models.TextField()
    idempotency_key = models.UUIDField()
    posted_at = models.DateTimeField(default=timezone.now)
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
    adjustment = models.ForeignKey(
        StockAdjustment,
        on_delete=models.PROTECT,
        related_name="lines",
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.PROTECT,
        related_name="stock_adjustment_lines",
    )
    quantity_signed = models.DecimalField(max_digits=18, decimal_places=4)
    unit_cost = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal("0.0000"),
        validators=[MinValueValidator(Decimal("0"))],
    )
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
    reference = models.CharField(max_length=64)
    source_warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="outgoing_stock_transfers",
    )
    destination_warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="incoming_stock_transfers",
    )
    reason = models.TextField(blank=True)
    idempotency_key = models.UUIDField()
    transferred_at = models.DateTimeField(default=timezone.now)
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
    transfer = models.ForeignKey(
        StockTransfer,
        on_delete=models.PROTECT,
        related_name="lines",
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.PROTECT,
        related_name="stock_transfer_lines",
    )
    quantity = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.0001"))],
    )
    unit_cost = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal("0.0000"),
        validators=[MinValueValidator(Decimal("0"))],
    )
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
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.PROTECT,
        related_name="stock_movements",
    )
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="stock_movements",
    )
    movement_type = models.CharField(max_length=32, choices=MovementType.choices)
    quantity_signed = models.DecimalField(max_digits=18, decimal_places=4)
    unit_cost = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal("0.0000"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    occurred_at = models.DateTimeField(default=timezone.now)
    source_type = models.CharField(max_length=32, choices=SourceType.choices)
    source_id = models.UUIDField()
    idempotency_key = models.UUIDField(unique=True)

    objects = ImmutableStockMovementQuerySet.as_manager()
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
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.PROTECT,
        related_name="stock_balances",
    )
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="stock_balances",
    )
    on_hand = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))
    reserved = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))
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
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.PROTECT,
        related_name="stock_reservations",
    )
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="stock_reservations",
    )
    quantity = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.0001"))],
    )
    source_type = models.CharField(max_length=32, choices=SourceType.choices)
    source_id = models.UUIDField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    idempotency_key = models.UUIDField()
    released_at = models.DateTimeField(null=True, blank=True)
    # Preserve original reserved quantity; consumption tracks partial shipments.
    fulfilled_quantity = models.DecimalField(max_digits=18, decimal_places=4, default=0)
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
