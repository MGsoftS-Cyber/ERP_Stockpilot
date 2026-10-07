# Sales domain services: authorize orders, reserve stock, ship and accept returns.
# Inventory fulfilment services own quantity posting; sales owns order/line state.
# Audit events explain the command, while immutable movements explain its stock effect.
"""Sales business rules. Each command commits all its changes or none of them."""

import hashlib
import json
import uuid
from decimal import Decimal, InvalidOperation

from django.db import transaction
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.inventory.fulfilment import consume_sales_reservation, post_customer_return
from apps.inventory.services import InventoryConflict, release_reservation, reserve_stock
from apps.sales.models import (
    CustomerReturn,
    CustomerReturnLine,
    SalesEvent,
    SalesOrder,
    SalesOrderLine,
    Shipment,
    ShipmentLine,
)
from apps.tenancy.models import Membership, Organization

SELLERS = ("ADMINISTRATOR", "MANAGER", "SALES_AGENT")
SHIPPERS = ("ADMINISTRATOR", "MANAGER", "STOCK_OPERATOR")


def authorize(organization, actor, roles):
    # A valid JWT alone is insufficient: verify current membership for every command.
    if (
        not actor.is_active
        or not Membership.objects.filter(
            organization=organization,
            organization__is_active=True,
            user=actor,
            is_active=True,
            role__in=roles,
        ).exists()
    ):
        raise PermissionDenied("Your role cannot perform this sales operation.")


def decimal_value(value, *, positive=False):
    # Avoid floating-point stock arithmetic and silently rounded input quantities.
    try:
        number = Decimal(str(value))
        if not number.is_finite() or abs(number) >= Decimal("100000000000000"):
            raise ValueError
        if number != number.quantize(Decimal("0.0001")):
            raise ValueError
        if number < 0 or (positive and number == 0):
            raise ValueError
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValidationError("Use a valid nonnegative decimal with at most four places.") from exc
    return number


def owned_active(record, organization):
    if record.organization_id != organization.pk or not record.is_active:
        raise ValidationError("Record is not active in the selected organization.")


def lock_tenant(organization):
    # Coarse per-tenant serialization also protects idempotency keys across orders.
    Organization.objects.select_for_update().get(pk=organization.pk)


def locked_order(organization, order_id):
    try:
        return SalesOrder.objects.select_for_update().get(pk=order_id, organization=organization)
    except SalesOrder.DoesNotExist as exc:
        raise NotFound("Sales order was not found.") from exc


def event(order, actor, action, detail=""):
    SalesEvent.objects.create(
        organization=order.organization,
        created_by=actor,
        order=order,
        action=action,
        detail=detail,
    )


def validated_lines(organization, lines):
    if not lines:
        raise ValidationError("A sales order needs at least one line.")
    seen, output = set(), []
    for line in lines:
        product = line["product"]
        owned_active(product, organization)
        if product.pk in seen:
            raise ValidationError("A product may appear only once per order.")
        seen.add(product.pk)
        quantity = decimal_value(line["quantity"], positive=True)
        if not product.unit.allows_decimals and quantity != quantity.to_integral_value():
            raise ValidationError("This product's unit requires whole quantities.")
        output.append(
            dict(
                product=product,
                quantity=quantity,
                unit_price=decimal_value(line["unit_price"]),
            )
        )
    return output


@transaction.atomic
def save_draft(*, organization, actor, customer, warehouse, lines, notes="", order_id=None):
    authorize(organization, actor, SELLERS)
    owned_active(customer, organization)
    owned_active(warehouse, organization)
    if customer.partner_type not in ("CUSTOMER", "BOTH"):
        raise ValidationError("Select a customer-capable business partner.")
    data = validated_lines(organization, lines)
    lock_tenant(organization)
    if order_id:
        order = locked_order(organization, order_id)
        if order.status != "DRAFT":
            raise InventoryConflict("Only a draft can be edited.")
        # Draft lines have no shipments/reservations and can safely be replaced.
        order.lines.all().delete()
        order.customer, order.warehouse, order.notes = customer, warehouse, notes
        order.save(update_fields=["customer", "warehouse", "notes", "updated_at"])
    else:
        order = SalesOrder.objects.create(
            organization=organization,
            created_by=actor,
            customer=customer,
            warehouse=warehouse,
            notes=notes,
            reference=f"SO-{uuid.uuid4().hex}",
        )
    for line in data:
        SalesOrderLine.objects.create(
            organization=organization, created_by=actor, order=order, **line
        )
    event(order, actor, "REVISED" if order_id else "CREATED")
    return order


@transaction.atomic
def confirm_order(*, organization, actor, order_id):
    authorize(organization, actor, SELLERS)
    lock_tenant(organization)
    order = locked_order(organization, order_id)
    if order.status == "CONFIRMED":
        return order  # Repeated confirmation cannot reserve twice.
    if order.status != "DRAFT":
        raise InventoryConflict("Only a draft can be confirmed.")
    owned_active(order.customer, organization)
    owned_active(order.warehouse, organization)
    if order.customer.partner_type not in ("CUSTOMER", "BOTH"):
        raise ValidationError("The selected partner is no longer a customer.")
    # Stable product order reduces deadlock risk when locking multiple balances.
    for line in order.lines.select_related("product__unit").order_by("product_id"):
        owned_active(line.product, organization)
        if (
            not line.product.unit.allows_decimals
            and line.quantity != line.quantity.to_integral_value()
        ):
            raise ValidationError("This product's unit now requires whole quantities.")
        line.unit_cost = decimal_value(line.product.purchase_price)
        line.reservation, _ = reserve_stock(
            organization=organization,
            actor=actor,
            product=line.product,
            warehouse=order.warehouse,
            quantity=line.quantity,
            source_type="SALES_ORDER",
            source_id=order.id,
            idempotency_key=uuid.uuid5(order.id, str(line.id)),
        )
        # Reject any pre-existing command-key collision instead of claiming unrelated stock.
        reservation = line.reservation
        if (
            reservation.source_type != "SALES_ORDER"
            or reservation.source_id != order.id
            or reservation.product_id != line.product_id
            or reservation.warehouse_id != order.warehouse_id
            or reservation.quantity != line.quantity
            or reservation.status != "ACTIVE"
        ):
            raise InventoryConflict("Reservation command key belongs to a different operation.")
        line.save(update_fields=["unit_cost", "reservation", "updated_at"])
    order.status = "CONFIRMED"
    order.save(update_fields=["status", "updated_at"])
    event(order, actor, "CONFIRMED", "All order quantities reserved.")
    return order


@transaction.atomic
def cancel_order(*, organization, actor, order_id, reason):
    authorize(organization, actor, SELLERS)
    if not reason.strip():
        raise ValidationError("Explain why the remaining order is cancelled.")
    lock_tenant(organization)
    order = locked_order(organization, order_id)
    if order.status == "CANCELLED":
        return order
    if order.status == "SHIPPED":
        raise InventoryConflict("A shipped order cannot be cancelled; record a return instead.")
    for line in order.lines.order_by("product_id"):
        if line.reservation_id:
            release_reservation(
                organization=organization,
                reservation_id=line.reservation_id,
                sales_order_id=order.id,
            )
    # Shipped history remains intact; only unshipped quantities are cancelled.
    order.status = "CANCELLED"
    order.save(update_fields=["status", "updated_at"])
    event(order, actor, "CANCELLED", reason.strip())
    return order


def normalized_command(lines, field):
    if not lines:
        raise ValidationError("Provide at least one positive quantity.")
    result = [(str(line[field]), decimal_value(line["quantity"], positive=True)) for line in lines]
    if len({key for key, _ in result}) != len(result):
        raise ValidationError("Do not repeat a document line.")
    return sorted(result)


def fingerprint(parent, lines, reason=""):
    payload = [str(parent), [(key, str(q.normalize())) for key, q in lines], reason]
    return hashlib.sha256(json.dumps(payload).encode()).hexdigest()


def replay(model, organization, key, payload_hash):
    previous = model.objects.filter(organization=organization, idempotency_key=key).first()
    if previous and previous.payload_hash != payload_hash:
        raise InventoryConflict("This command key was already used for different data.")
    return previous


@transaction.atomic
def ship_order(*, organization, actor, order_id, lines, idempotency_key):
    authorize(organization, actor, SHIPPERS)
    data = normalized_command(lines, "order_line")
    digest = fingerprint(order_id, data)
    lock_tenant(organization)
    order = locked_order(organization, order_id)
    previous = replay(Shipment, organization, idempotency_key, digest)
    if previous:
        return previous, False
    if order.status not in ("CONFIRMED", "PARTIALLY_SHIPPED"):
        raise InventoryConflict("Confirm the order before shipping; cancelled orders cannot ship.")
    available_lines = {str(line.pk): line for line in order.lines.select_related("product__unit")}
    for key, quantity in data:
        line = available_lines.get(key)
        if line is None or quantity > line.quantity - line.shipped_quantity:
            raise InventoryConflict("Shipment exceeds this order's remaining quantity.")
        if not line.product.unit.allows_decimals and quantity != quantity.to_integral_value():
            raise ValidationError("This product's unit requires whole quantities.")
    shipment = Shipment.objects.create(
        organization=organization,
        created_by=actor,
        order=order,
        idempotency_key=idempotency_key,
        payload_hash=digest,
    )
    for key, quantity in sorted(data, key=lambda row: str(available_lines[row[0]].product_id)):
        line = available_lines[key]
        shipped = ShipmentLine.objects.create(
            organization=organization,
            created_by=actor,
            shipment=shipment,
            order_line=line,
            quantity=quantity,
        )
        consume_sales_reservation(
            organization=organization,
            actor=actor,
            reservation_id=line.reservation_id,
            order_id=order.id,
            quantity=quantity,
            unit_cost=line.unit_cost,
            shipment_id=shipment.id,
            line_id=shipped.id,
        )
        line.shipped_quantity += quantity
        line.save(update_fields=["shipped_quantity", "updated_at"])
    order.status = (
        "SHIPPED"
        if all(line.shipped_quantity == line.quantity for line in available_lines.values())
        else "PARTIALLY_SHIPPED"
    )
    order.save(update_fields=["status", "updated_at"])
    event(order, actor, "SHIPPED", f"Shipment {shipment.id}")
    return shipment, True


@transaction.atomic
def return_goods(*, organization, actor, shipment_id, lines, reason, idempotency_key):
    authorize(organization, actor, SHIPPERS)
    reason = reason.strip()
    if not reason:
        raise ValidationError("A customer return needs a reason.")
    data = normalized_command(lines, "shipment_line")
    digest = fingerprint(shipment_id, data, reason)
    lock_tenant(organization)
    try:
        shipment = Shipment.objects.get(pk=shipment_id, organization=organization)
    except Shipment.DoesNotExist as exc:
        raise NotFound("Shipment was not found.") from exc
    order = locked_order(organization, shipment.order_id)
    previous = replay(CustomerReturn, organization, idempotency_key, digest)
    if previous:
        return previous, False
    choices = {
        str(line.pk): line for line in shipment.lines.select_related("order_line__product__unit")
    }
    for key, quantity in data:
        line = choices.get(key)
        if line is None or quantity > line.quantity - line.returned_quantity:
            raise InventoryConflict("Return exceeds the unreturned shipped quantity.")
        if (
            not line.order_line.product.unit.allows_decimals
            and quantity != quantity.to_integral_value()
        ):
            raise ValidationError("This product's unit requires whole quantities.")
    returned = CustomerReturn.objects.create(
        organization=organization,
        created_by=actor,
        shipment=shipment,
        reason=reason,
        idempotency_key=idempotency_key,
        payload_hash=digest,
    )
    for key, quantity in sorted(data, key=lambda row: str(choices[row[0]].order_line.product_id)):
        line = choices[key]
        document_line = CustomerReturnLine.objects.create(
            organization=organization,
            created_by=actor,
            customer_return=returned,
            shipment_line=line,
            quantity=quantity,
        )
        post_customer_return(
            organization=organization,
            actor=actor,
            product=line.order_line.product,
            warehouse=order.warehouse,
            quantity=quantity,
            unit_cost=line.order_line.unit_cost,
            return_id=returned.id,
            line_id=document_line.id,
        )
        line.returned_quantity += quantity
        line.save(update_fields=["returned_quantity", "updated_at"])
    # A return does not reopen fulfilment or reserve the returned items again.
    event(order, actor, "RETURNED", f"Return {returned.id}: {reason}")
    return returned, True
