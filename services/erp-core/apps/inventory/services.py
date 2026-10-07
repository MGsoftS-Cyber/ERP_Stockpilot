# Inventory command layer: validates quantities and appends stock movements atomically.
# Balances and document lines change in the same transaction; failure rolls back the entire command.
# Purchasing and sales reuse this ledger so the ERP has one stock accounting system.
# Teaching edition: Perform business operations after checking the tenant and input.
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound, ValidationError

from apps.catalog.models import Product
from apps.inventory.models import (
    StockAdjustment,
    StockAdjustmentLine,
    StockBalance,
    StockMovement,
    StockReservation,
    StockTransfer,
    StockTransferLine,
    Warehouse,
)


class InventoryConflict(APIException):
    status_code = 409
    default_code = "inventory_conflict"
    default_detail = "The inventory operation conflicts with the current stock state."


class InsufficientStock(InventoryConflict):
    default_code = "insufficient_stock"
    default_detail = "The operation would make available stock negative."


# Provide the inventory posting boundary for purchasing.
@transaction.atomic
def post_purchase_receipt_movement(
    *,
    organization,
    actor,
    product,
    warehouse,
    quantity,
    unit_cost,
    receipt_id,
    idempotency_key,
):
    """Internal trusted-service API; purchasing owns receipt authorization/idempotency."""
    _assert_organization(product, organization, "product")
    _assert_organization(warehouse, organization, "warehouse")
    if quantity <= 0:
        raise ValidationError("Receipt quantity must be positive.")
    return _post_movement(
        organization=organization,
        actor=actor,
        product=product,
        warehouse=warehouse,
        movement_type=StockMovement.MovementType.PURCHASE_RECEIPT,
        quantity_signed=quantity,
        unit_cost=unit_cost,
        occurred_at=timezone.now(),
        source_type=StockMovement.SourceType.PURCHASE_RECEIPT,
        source_id=receipt_id,
        idempotency_key=idempotency_key,
    )


@dataclass(frozen=True)
class ReconciliationItem:
    product_id: uuid.UUID
    warehouse_id: uuid.UUID
    ledger_total: Decimal
    balance_on_hand: Decimal

    @property
    def is_reconciled(self) -> bool:
        return self.ledger_total == self.balance_on_hand


@transaction.atomic
def create_warehouse(*, organization, actor, data: dict[str, Any]) -> Warehouse:
    warehouse = Warehouse(organization=organization, created_by=actor, **data)
    warehouse.full_clean()
    warehouse.save()
    return warehouse


# Reject related data that belongs to another company.
def _assert_organization(record, organization, field: str) -> None:
    if record.organization_id != organization.id:
        raise ValidationError({field: "Must belong to the selected organization."})


# Derive a stable key from the logical command source.
def _movement_idempotency_key(*parts: object) -> uuid.UUID:
    value = ":".join(str(part) for part in parts)
    return uuid.uuid5(uuid.NAMESPACE_URL, f"stockpilot:movement:{value}")


# Lock or safely create the product/warehouse projection.
def _lock_balance(*, organization, product, warehouse, actor) -> StockBalance:
    try:
        return StockBalance.objects.select_for_update().get(
            organization=organization,
            product=product,
            warehouse=warehouse,
        )
    except StockBalance.DoesNotExist:
        try:
            with transaction.atomic():
                StockBalance.objects.create(
                    organization=organization,
                    product=product,
                    warehouse=warehouse,
                    created_by=actor,
                )
        except IntegrityError:
            pass
        return StockBalance.objects.select_for_update().get(
            organization=organization,
            product=product,
            warehouse=warehouse,
        )


# Append the ledger entry and update its locked projection together.
def _post_movement(
    *,
    organization,
    actor,
    product,
    warehouse,
    movement_type: str,
    quantity_signed: Decimal,
    unit_cost: Decimal,
    occurred_at,
    source_type: str,
    source_id: uuid.UUID,
    idempotency_key: uuid.UUID,
    locked_balance: StockBalance | None = None,
) -> StockMovement:
    if quantity_signed == 0:
        raise ValidationError({"quantity_signed": "Must not be zero."})
    if unit_cost < 0:
        raise ValidationError({"unit_cost": "Must not be negative."})

    balance = locked_balance or _lock_balance(
        organization=organization,
        product=product,
        warehouse=warehouse,
        actor=actor,
    )
    new_on_hand = balance.on_hand + quantity_signed
    if new_on_hand < balance.reserved:
        raise InsufficientStock(
            f"Only {balance.available} units are available for {product.sku} "
            f"in warehouse {warehouse.code}."
        )

    movement = StockMovement.objects.create(
        organization=organization,
        created_by=actor,
        product=product,
        warehouse=warehouse,
        movement_type=movement_type,
        quantity_signed=quantity_signed,
        unit_cost=unit_cost,
        occurred_at=occurred_at,
        source_type=source_type,
        source_id=source_id,
        idempotency_key=idempotency_key,
    )
    balance.on_hand = new_on_hand
    balance.save(update_fields=["on_hand", "updated_at"])
    return movement


# Post signed corrections without rewriting earlier movements.
@transaction.atomic
def post_stock_adjustment(
    *,
    organization,
    actor,
    warehouse: Warehouse,
    lines: list[dict[str, Any]],
    reason: str,
    idempotency_key: uuid.UUID,
    reference: str = "",
) -> tuple[StockAdjustment, bool]:
    existing = StockAdjustment.objects.filter(
        organization=organization,
        idempotency_key=idempotency_key,
    ).first()
    if existing:
        return existing, False

    _assert_organization(warehouse, organization, "warehouse")
    if not lines:
        raise ValidationError({"lines": "At least one adjustment line is required."})

    product_ids = [line["product"].id for line in lines]
    if len(product_ids) != len(set(product_ids)):
        raise ValidationError({"lines": "A product can appear only once."})

    if (
        reference
        and StockAdjustment.objects.filter(
            organization=organization,
            reference=reference,
        ).exists()
    ):
        raise ValidationError({"reference": "This reference already exists."})

    document_id = uuid.uuid4()
    adjustment = StockAdjustment.objects.create(
        id=document_id,
        organization=organization,
        created_by=actor,
        reference=reference or f"ADJ-{document_id.hex[:10].upper()}",
        warehouse=warehouse,
        reason=reason,
        idempotency_key=idempotency_key,
    )

    for line_data in sorted(lines, key=lambda item: str(item["product"].id)):
        product: Product = line_data["product"]
        quantity_signed = Decimal(line_data["quantity_signed"])
        unit_cost = Decimal(line_data.get("unit_cost", 0))
        _assert_organization(product, organization, "product")
        if quantity_signed == 0:
            raise ValidationError({"quantity_signed": "Must not be zero."})
        if unit_cost < 0:
            raise ValidationError({"unit_cost": "Must not be negative."})

        line = StockAdjustmentLine.objects.create(
            organization=organization,
            created_by=actor,
            adjustment=adjustment,
            product=product,
            quantity_signed=quantity_signed,
            unit_cost=unit_cost,
        )
        movement_type = (
            StockMovement.MovementType.ADJUSTMENT_IN
            if quantity_signed > 0
            else StockMovement.MovementType.ADJUSTMENT_OUT
        )
        _post_movement(
            organization=organization,
            actor=actor,
            product=product,
            warehouse=warehouse,
            movement_type=movement_type,
            quantity_signed=quantity_signed,
            unit_cost=unit_cost,
            occurred_at=adjustment.posted_at,
            source_type=StockMovement.SourceType.STOCK_ADJUSTMENT,
            source_id=adjustment.id,
            idempotency_key=_movement_idempotency_key(idempotency_key, line.id),
        )

    return adjustment, True


# Post equal source/destination movements in one transaction.
@transaction.atomic
def transfer_stock(
    *,
    organization,
    actor,
    source_warehouse: Warehouse,
    destination_warehouse: Warehouse,
    lines: list[dict[str, Any]],
    idempotency_key: uuid.UUID,
    reference: str = "",
    reason: str = "",
) -> tuple[StockTransfer, bool]:
    existing = StockTransfer.objects.filter(
        organization=organization,
        idempotency_key=idempotency_key,
    ).first()
    if existing:
        return existing, False

    _assert_organization(source_warehouse, organization, "source_warehouse")
    _assert_organization(destination_warehouse, organization, "destination_warehouse")
    if source_warehouse.id == destination_warehouse.id:
        raise ValidationError({"destination_warehouse": "Must differ from source warehouse."})
    if not lines:
        raise ValidationError({"lines": "At least one transfer line is required."})

    product_ids = [line["product"].id for line in lines]
    if len(product_ids) != len(set(product_ids)):
        raise ValidationError({"lines": "A product can appear only once."})

    if (
        reference
        and StockTransfer.objects.filter(
            organization=organization,
            reference=reference,
        ).exists()
    ):
        raise ValidationError({"reference": "This reference already exists."})

    document_id = uuid.uuid4()
    transfer = StockTransfer.objects.create(
        id=document_id,
        organization=organization,
        created_by=actor,
        reference=reference or f"TRF-{document_id.hex[:10].upper()}",
        source_warehouse=source_warehouse,
        destination_warehouse=destination_warehouse,
        reason=reason,
        idempotency_key=idempotency_key,
    )

    for line_data in sorted(lines, key=lambda item: str(item["product"].id)):
        product: Product = line_data["product"]
        quantity = Decimal(line_data["quantity"])
        unit_cost = Decimal(line_data.get("unit_cost", 0))
        _assert_organization(product, organization, "product")
        if quantity <= 0:
            raise ValidationError({"quantity": "Must be greater than zero."})
        if unit_cost < 0:
            raise ValidationError({"unit_cost": "Must not be negative."})

        line = StockTransferLine.objects.create(
            organization=organization,
            created_by=actor,
            transfer=transfer,
            product=product,
            quantity=quantity,
            unit_cost=unit_cost,
        )

        warehouses = sorted(
            [source_warehouse, destination_warehouse],
            key=lambda item: str(item.id),
        )
        locked = {
            warehouse.id: _lock_balance(
                organization=organization,
                product=product,
                warehouse=warehouse,
                actor=actor,
            )
            for warehouse in warehouses
        }
        _post_movement(
            organization=organization,
            actor=actor,
            product=product,
            warehouse=source_warehouse,
            movement_type=StockMovement.MovementType.TRANSFER_OUT,
            quantity_signed=-quantity,
            unit_cost=unit_cost,
            occurred_at=transfer.transferred_at,
            source_type=StockMovement.SourceType.STOCK_TRANSFER,
            source_id=transfer.id,
            idempotency_key=_movement_idempotency_key(idempotency_key, line.id, "out"),
            locked_balance=locked[source_warehouse.id],
        )
        _post_movement(
            organization=organization,
            actor=actor,
            product=product,
            warehouse=destination_warehouse,
            movement_type=StockMovement.MovementType.TRANSFER_IN,
            quantity_signed=quantity,
            unit_cost=unit_cost,
            occurred_at=transfer.transferred_at,
            source_type=StockMovement.SourceType.STOCK_TRANSFER,
            source_id=transfer.id,
            idempotency_key=_movement_idempotency_key(idempotency_key, line.id, "in"),
            locked_balance=locked[destination_warehouse.id],
        )

    return transfer, True


# Allocate available units without changing physical on-hand stock.
@transaction.atomic
def reserve_stock(
    *,
    organization,
    actor,
    product: Product,
    warehouse: Warehouse,
    quantity: Decimal,
    source_type: str,
    source_id: uuid.UUID,
    idempotency_key: uuid.UUID,
) -> tuple[StockReservation, bool]:
    existing = StockReservation.objects.filter(
        organization=organization,
        idempotency_key=idempotency_key,
    ).first()
    if existing:
        return existing, False

    _assert_organization(product, organization, "product")
    _assert_organization(warehouse, organization, "warehouse")
    quantity = Decimal(quantity)
    if quantity <= 0:
        raise ValidationError({"quantity": "Must be greater than zero."})

    balance = _lock_balance(
        organization=organization,
        product=product,
        warehouse=warehouse,
        actor=actor,
    )
    if quantity > balance.available:
        raise InsufficientStock(f"Only {balance.available} units are available for reservation.")

    reservation = StockReservation.objects.create(
        organization=organization,
        created_by=actor,
        product=product,
        warehouse=warehouse,
        quantity=quantity,
        source_type=source_type,
        source_id=source_id,
        idempotency_key=idempotency_key,
    )
    balance.reserved += quantity
    balance.save(update_fields=["reserved", "updated_at"])
    return reservation, True


# Free only unfulfilled units and preserve the allocation history.
@transaction.atomic
def release_reservation(
    *, organization, reservation_id: uuid.UUID, sales_order_id=None
) -> StockReservation:
    try:
        reservation = StockReservation.objects.select_for_update().get(
            id=reservation_id,
            organization=organization,
        )
    except StockReservation.DoesNotExist as exc:
        raise NotFound("Stock reservation was not found.") from exc

    # Sales owns this reservation: a manual API release must not invalidate an order.
    if reservation.source_type == "SALES_ORDER" and reservation.source_id != sales_order_id:
        raise InventoryConflict("Cancel the sales order to release its remaining reservation.")
    if reservation.status != StockReservation.Status.ACTIVE:
        return reservation

    balance = _lock_balance(
        organization=organization,
        product=reservation.product,
        warehouse=reservation.warehouse,
        actor=reservation.created_by,
    )
    balance.reserved -= reservation.quantity - reservation.fulfilled_quantity
    balance.save(update_fields=["reserved", "updated_at"])
    reservation.status = StockReservation.Status.RELEASED
    reservation.released_at = timezone.now()
    reservation.save(update_fields=["status", "released_at", "updated_at"])
    return reservation


# Compare ledger sums with the current on-hand projection.
def reconciliation_report(*, organization) -> list[ReconciliationItem]:
    balances = StockBalance.objects.for_organization(organization).values(
        "product_id",
        "warehouse_id",
        "on_hand",
    )
    ledger_totals = {
        (row["product_id"], row["warehouse_id"]): row["total"] or Decimal("0")
        for row in StockMovement.objects.for_organization(organization)
        .values("product_id", "warehouse_id")
        .annotate(total=Sum("quantity_signed"))
    }
    items = []
    for balance in balances:
        key = (balance["product_id"], balance["warehouse_id"])
        items.append(
            ReconciliationItem(
                product_id=balance["product_id"],
                warehouse_id=balance["warehouse_id"],
                ledger_total=ledger_totals.pop(key, Decimal("0")),
                balance_on_hand=balance["on_hand"],
            )
        )
    for (product_id, warehouse_id), ledger_total in ledger_totals.items():
        items.append(
            ReconciliationItem(
                product_id=product_id,
                warehouse_id=warehouse_id,
                ledger_total=ledger_total,
                balance_on_hand=Decimal("0"),
            )
        )
    return items
