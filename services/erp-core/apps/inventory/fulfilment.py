# Inventory fulfilment boundary: sales calls these services to reserve, consume or return goods.
# Reservations, shipment movements and balance changes must stay consistent within one transaction.
# Sales must not update StockBalance directly.
"""Week 5 public inventory services: sales never writes a StockBalance directly."""

import uuid

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound

from apps.inventory.models import StockMovement, StockReservation
from apps.inventory.services import (
    InventoryConflict,
    _assert_organization,
    _lock_balance,
    _post_movement,
)


@transaction.atomic
def consume_sales_reservation(
    *, organization, actor, reservation_id, order_id, quantity, unit_cost, shipment_id, line_id
):
    # Lock reservation before balance, matching the release operation's lock order.
    try:
        reservation = StockReservation.objects.select_for_update().get(
            pk=reservation_id,
            organization=organization,
            source_type="SALES_ORDER",
            source_id=order_id,
        )
    except StockReservation.DoesNotExist as exc:
        raise NotFound("Sales reservation was not found.") from exc
    remaining = reservation.quantity - reservation.fulfilled_quantity
    if reservation.status != "ACTIVE" or quantity <= 0 or quantity > remaining:
        raise InventoryConflict("Shipment exceeds the active reserved quantity.")
    balance = _lock_balance(
        organization=organization,
        actor=actor,
        product=reservation.product,
        warehouse=reservation.warehouse,
    )
    # Free only the units being shipped before the negative physical movement.
    balance.reserved -= quantity
    balance.save(update_fields=["reserved", "updated_at"])
    movement = _post_movement(
        organization=organization,
        actor=actor,
        product=reservation.product,
        warehouse=reservation.warehouse,
        quantity_signed=-quantity,
        unit_cost=unit_cost,
        movement_type=StockMovement.MovementType.SALE_SHIPMENT,
        source_type="SHIPMENT",
        source_id=shipment_id,
        occurred_at=timezone.now(),
        idempotency_key=uuid.uuid5(shipment_id, str(line_id)),
        locked_balance=balance,
    )
    reservation.fulfilled_quantity += quantity
    if reservation.fulfilled_quantity == reservation.quantity:
        reservation.status = StockReservation.Status.FULFILLED
    reservation.save(update_fields=["fulfilled_quantity", "status", "updated_at"])
    return movement


@transaction.atomic
def post_customer_return(
    *, organization, actor, product, warehouse, quantity, unit_cost, return_id, line_id
):
    # A validated sales return restores stock to the original shipping warehouse.
    _assert_organization(product, organization, "product")
    _assert_organization(warehouse, organization, "warehouse")
    if quantity <= 0:
        raise InventoryConflict("Return quantity must be positive.")
    return _post_movement(
        organization=organization,
        actor=actor,
        product=product,
        warehouse=warehouse,
        quantity_signed=quantity,
        unit_cost=unit_cost,
        movement_type=StockMovement.MovementType.CUSTOMER_RETURN,
        source_type="CUSTOMER_RETURN",
        source_id=return_id,
        occurred_at=timezone.now(),
        idempotency_key=uuid.uuid5(return_id, str(line_id)),
    )
