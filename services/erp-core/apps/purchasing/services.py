# Purchase domain services: control draft, approval and receipt state transitions.
# A receipt validates remaining quantities and posts incoming inventory movements atomically.
# Billing later creates the financial invoice; receiving goods alone does not record payment.
# Teaching edition: Perform business operations after checking the tenant and input.
import hashlib
import json
import uuid
from decimal import Decimal, InvalidOperation

from django.db import transaction
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.inventory.models import StockMovement
from apps.inventory.services import InventoryConflict, post_purchase_receipt_movement
from apps.purchasing.models import (
    GoodsReceipt,
    GoodsReceiptLine,
    PurchaseEvent,
    PurchaseOrder,
    PurchaseOrderLine,
)
from apps.tenancy.models import Membership, Organization

MANAGERS = (Membership.Role.ADMINISTRATOR, Membership.Role.MANAGER)
BUYERS = (*MANAGERS, Membership.Role.PURCHASING_AGENT)
RECEIVERS = (*BUYERS, Membership.Role.STOCK_OPERATOR)


# Check the current membership, not a browser-supplied role.
def authorize(organization, actor, roles):
    if not Membership.objects.filter(
        organization=organization,
        user=actor,
        is_active=True,
        organization__is_active=True,
        role__in=roles,
    ).exists():
        raise PermissionDenied("This purchasing action is not permitted.")


# Reject excess precision, negative values and non-finite numbers.
def decimal_value(value, *, positive=False):
    try:
        value = Decimal(str(value))
        valid = value.is_finite() and abs(value) < Decimal("1e14")
        valid = valid and value == value.quantize(Decimal("0.0001"))
        valid = valid and (value > 0 if positive else value >= 0)
    except (InvalidOperation, ValueError, TypeError):
        valid = False
    if not valid:
        raise ValidationError("Use a valid decimal with at most four decimal places.")
    return value


# Ensure related master data is active in this company.
def owned(record, organization):
    if record.organization_id != organization.id or not record.is_active:
        raise ValidationError("Related records must be active and belong to this organization.")


# Record actor, action and detail beside the purchase document.
def event(order, actor, action, detail=""):
    PurchaseEvent.objects.create(
        organization=order.organization,
        created_by=actor,
        order=order,
        action=action,
        detail=detail,
    )


# Retrieve the tenant-owned order while holding a row lock.
def locked_order(organization, order_id):
    try:
        return PurchaseOrder.objects.select_for_update().get(organization=organization, pk=order_id)
    except PurchaseOrder.DoesNotExist as exc:
        raise NotFound("Purchase order not found.") from exc


# Validate supplier and product lines, then save a draft purchase.
@transaction.atomic
def create_order(*, organization, actor, supplier, lines, notes=""):
    authorize(organization, actor, BUYERS)
    owned(supplier, organization)
    if supplier.partner_type not in ("SUPPLIER", "BOTH"):
        raise ValidationError("Select a supplier, not a customer-only partner.")
    if not lines or len({str(line["product"].id) for line in lines}) != len(lines):
        raise ValidationError("Provide nonempty lines with distinct products.")
    order_id = uuid.uuid4()
    order = PurchaseOrder.objects.create(
        id=order_id,
        organization=organization,
        created_by=actor,
        reference=f"PO-{order_id.hex.upper()}",
        supplier=supplier,
        notes=notes,
    )
    for line in lines:
        owned(line["product"], organization)
        PurchaseOrderLine.objects.create(
            organization=organization,
            created_by=actor,
            order=order,
            product=line["product"],
            quantity=decimal_value(line["quantity"], positive=True),
            unit_price=decimal_value(line["unit_price"]),
        )
    event(order, actor, "CREATED")
    return order


# Lock the draft before replacing its line collection.
@transaction.atomic
def revise_order(*, organization, actor, order_id, supplier, lines, notes=""):
    authorize(organization, actor, BUYERS)
    order = locked_order(organization, order_id)
    if order.status != "DRAFT":
        raise InventoryConflict("Only draft orders can be edited.")
    owned(supplier, organization)
    if supplier.partner_type not in ("SUPPLIER", "BOTH"):
        raise ValidationError("Select a supplier.")
    if not lines or len({str(line["product"].id) for line in lines}) != len(lines):
        raise ValidationError("Provide nonempty lines with distinct products.")
    order.lines.all().delete()
    for line in lines:
        owned(line["product"], organization)
        PurchaseOrderLine.objects.create(
            organization=organization,
            created_by=actor,
            order=order,
            product=line["product"],
            quantity=decimal_value(line["quantity"], positive=True),
            unit_price=decimal_value(line["unit_price"]),
        )
    order.supplier = supplier
    order.notes = notes
    order.save(update_fields=["supplier", "notes", "updated_at"])
    event(order, actor, "REVISED")
    return order


# Validate action-specific authority and the legal state transition.
@transaction.atomic
def transition_order(*, organization, actor, order_id, action, reason=""):
    authorize(
        organization,
        actor,
        MANAGERS if action in ("approve", "return_to_draft", "close") else BUYERS,
    )
    order = locked_order(organization, order_id)
    transitions = {
        "submit": (("DRAFT",), "SUBMITTED"),
        "approve": (("SUBMITTED",), "APPROVED"),
        "return_to_draft": (("SUBMITTED",), "DRAFT"),
        "cancel": (("DRAFT", "SUBMITTED", "APPROVED"), "CANCELLED"),
        "close": (("RECEIVED",), "CLOSED"),
    }
    if action not in transitions or order.status not in transitions[action][0]:
        raise InventoryConflict("Invalid purchase-order state transition.")
    if action in ("return_to_draft", "close") and not reason.strip():
        raise ValidationError("A reason is required for correction or closure.")
    if action == "cancel" and order.lines.filter(received_quantity__gt=0).exists():
        raise InventoryConflict("Cannot cancel an order with received goods.")
    order.status = transitions[action][1]
    order.save(update_fields=["status", "updated_at"])
    event(order, actor, action.upper(), reason)
    return order


# Commit receipt, inventory posting and order quantities together.
@transaction.atomic
def receive_goods(*, organization, actor, order_id, warehouse, lines, idempotency_key):
    authorize(organization, actor, RECEIVERS)
    owned(warehouse, organization)
    if not lines or len({str(line["order_line"]) for line in lines}) != len(lines):
        raise ValidationError("Provide nonempty receipt lines without duplicates.")
    normalized = sorted(
        [
            [
                str(line["order_line"]),
                str(decimal_value(line["quantity"], positive=True).normalize()),
            ]
            for line in lines
        ]
    )
    fingerprint = hashlib.sha256(
        json.dumps([str(order_id), str(warehouse.id), normalized]).encode()
    ).hexdigest()
    # Coarse tenant lock deliberately serializes Week 4 receipts, including duplicate
    # keys across different orders. Replace with a command registry if scale requires it.
    Organization.objects.select_for_update().get(pk=organization.id)
    order = locked_order(organization, order_id)
    existing = GoodsReceipt.objects.filter(
        organization=organization, idempotency_key=idempotency_key
    ).first()
    if existing:
        if existing.payload_hash != fingerprint:
            raise InventoryConflict("Idempotency key already used with a different payload.")
        return existing, False
    if order.status not in ("APPROVED", "PARTIALLY_RECEIVED"):
        raise InventoryConflict("Only approved orders can receive goods.")
    order_lines = {str(line.id): line for line in order.lines.select_related("product")}
    for line_id, qty in normalized:
        if line_id not in order_lines:
            raise ValidationError("Receipt line does not belong to this purchase order.")
        line = order_lines[line_id]
        if line.received_quantity + Decimal(qty) > line.quantity:
            raise InventoryConflict("Receipt exceeds the remaining ordered quantity.")
    receipt = GoodsReceipt.objects.create(
        organization=organization,
        created_by=actor,
        order=order,
        warehouse=warehouse,
        idempotency_key=idempotency_key,
        payload_hash=fingerprint,
    )
    # Match Week 3's product lock ordering.
    for line_id, qty in sorted(normalized, key=lambda pair: str(order_lines[pair[0]].product_id)):
        line = order_lines[line_id]
        quantity = Decimal(qty)
        GoodsReceiptLine.objects.create(
            organization=organization,
            created_by=actor,
            receipt=receipt,
            order_line=line,
            quantity=quantity,
        )
        post_purchase_receipt_movement(
            organization=organization,
            actor=actor,
            product=line.product,
            warehouse=warehouse,
            quantity=quantity,
            unit_cost=line.unit_price,
            receipt_id=receipt.id,
            idempotency_key=uuid.uuid5(receipt.id, str(line.id)),
        )
        line.received_quantity += quantity
        line.save(update_fields=["received_quantity", "updated_at"])
    order.status = (
        "RECEIVED"
        if all(line.received_quantity == line.quantity for line in order_lines.values())
        else "PARTIALLY_RECEIVED"
    )
    order.save(update_fields=["status", "updated_at"])
    event(order, actor, StockMovement.MovementType.PURCHASE_RECEIPT, str(receipt.id))
    return receipt, True
