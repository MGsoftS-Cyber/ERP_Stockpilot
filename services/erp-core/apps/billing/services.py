# Billing domain services: validate draft invoices, post fixed amounts and allocate payments.
# Orders supply eligible source lines; accounting values use Decimal and remain separated by
# currency.
# Posting finance records does not bypass inventory shipment or receipt services.
"""Financial workflow. Posting invoices never writes inventory quantities."""

from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.audit.services import record
from apps.catalog.models import Product
from apps.common.commands import (
    FINANCE_ROLES,
    Conflict,
    authorize,
    digest,
    lock_organization,
    money,
    number,
    replay,
)
from apps.partners.models import BusinessPartner
from apps.purchasing.models import PurchaseOrder
from apps.sales.models import SalesOrder

from .models import Invoice, InvoiceLine, Payment, PaymentAllocation


@transaction.atomic
def create_invoice(
    *,
    organization,
    actor,
    idempotency_key,
    kind,
    partner_id,
    reference,
    currency,
    issued_on,
    due_on,
    lines,
    sales_order_id=None,
    purchase_order_id=None,
):
    authorize(organization, actor, FINANCE_ROLES)
    lock_organization(organization)
    payload_hash = digest(
        dict(
            kind=kind,
            partner_id=partner_id,
            reference=reference,
            currency=currency,
            issued_on=issued_on,
            due_on=due_on,
            lines=lines,
            sales_order_id=sales_order_id,
            purchase_order_id=purchase_order_id,
        )
    )
    previous = replay(Invoice, organization, idempotency_key, payload_hash)
    if previous:
        return previous, False
    if kind not in Invoice.Kind.values or currency not in ("DZD", "EUR", "USD"):
        raise ValidationError("Choose CUSTOMER/SUPPLIER and DZD/EUR/USD.")
    if not reference.strip() or len(reference) > 64 or due_on < issued_on:
        raise ValidationError("A reference and valid issue/due dates are required.")
    partner = BusinessPartner.objects.filter(
        pk=partner_id, organization=organization, is_active=True, partner_type__in=[kind, "BOTH"]
    ).first()
    if partner is None:
        raise ValidationError("Choose an active partner of the correct type in this organization.")
    if Invoice.objects.filter(
        organization=organization, kind=kind, partner=partner, reference=reference
    ).exists():
        raise Conflict("This partner/reference already has an invoice.")
    source = None
    if sales_order_id and purchase_order_id:
        raise ValidationError("An invoice can have only one source order.")
    if sales_order_id or purchase_order_id:
        # Whole-order billing is explicit; no silent partial-quantity interpretation.
        if lines:
            raise ValidationError("Source-order invoices derive their lines from the order.")
        if sales_order_id:
            source = SalesOrder.objects.filter(
                pk=sales_order_id,
                organization=organization,
                customer=partner,
                status__in=["CONFIRMED", "PARTIALLY_SHIPPED", "SHIPPED"],
            ).first()
            correct_kind = kind == "CUSTOMER"
        else:
            source = PurchaseOrder.objects.filter(
                pk=purchase_order_id,
                organization=organization,
                supplier=partner,
                status__in=["APPROVED", "PARTIALLY_RECEIVED", "RECEIVED", "CLOSED"],
            ).first()
            correct_kind = kind == "SUPPLIER"
        if source is None or not correct_kind:
            raise ValidationError("The source order, partner, kind or state is invalid.")
        field = "sales_order" if sales_order_id else "purchase_order"
        if Invoice.objects.filter(**{field: source}).exists():
            raise Conflict("This order already has an invoice, including voided history.")
        lines = [
            dict(
                product_id=line.product_id,
                description=line.product.name,
                quantity=line.quantity,
                unit_price=line.unit_price,
                unit_cost=getattr(line, "unit_cost", line.unit_price),
                tax_rate=line.product.tax_rate.rate if line.product.tax_rate else 0,
            )
            for line in source.lines.select_related("product__tax_rate")
        ]
    if not lines or len(lines) > 100:
        raise ValidationError("An invoice requires between 1 and 100 lines.")
    invoice = Invoice.objects.create(
        organization=organization,
        created_by=actor,
        partner=partner,
        kind=kind,
        reference=reference,
        currency=currency,
        issued_on=issued_on,
        due_on=due_on,
        sales_order_id=sales_order_id,
        purchase_order_id=purchase_order_id,
        idempotency_key=idempotency_key,
        payload_hash=payload_hash,
    )
    subtotal = tax_total = cost_total = Decimal(0)
    for item in lines:
        product = None
        if item.get("product_id"):
            product = Product.objects.filter(
                pk=item["product_id"], organization=organization
            ).first()
            if product is None:
                raise ValidationError("Invoice products must belong to this organization.")
        quantity = number(item["quantity"], positive=True)
        price = number(item["unit_price"])
        cost = number(item.get("unit_cost", product.purchase_price if product else 0))
        tax_rate = number(item.get("tax_rate", 0), places=2)
        description = item["description"].strip()
        if tax_rate > 100 or not description or len(description) > 240:
            raise ValidationError("Check line description and tax percentage (0–100).")
        net = money(quantity * price)
        tax = money(net * tax_rate / 100)
        subtotal += net
        tax_total += tax
        cost_total += money(quantity * cost)
        if max(subtotal + tax_total, cost_total) >= Decimal("1000000000000000"):
            raise ValidationError("Invoice totals exceed the supported amount.")
        InvoiceLine.objects.create(
            organization=organization,
            created_by=actor,
            invoice=invoice,
            product=product,
            description=description,
            quantity=quantity,
            unit_price=price,
            unit_cost=cost,
            tax_rate=tax_rate,
            net=net,
            tax=tax,
        )
    invoice.subtotal, invoice.tax_total = subtotal, tax_total
    invoice.total, invoice.cost_total = subtotal + tax_total, cost_total
    invoice.save()
    record(organization, actor, "billing.draft_created", invoice, total=str(invoice.total))
    return invoice, True


@transaction.atomic
def change_status(*, organization, actor, invoice_id, target, reason=""):
    authorize(organization, actor, FINANCE_ROLES)
    lock_organization(organization)
    invoice = (
        Invoice.objects.select_for_update().filter(pk=invoice_id, organization=organization).first()
    )
    if invoice is None:
        raise ValidationError("Invoice not found in this organization.")
    if target not in ("POSTED", "VOID"):
        raise ValidationError("Unsupported transition.")
    if invoice.status == target:
        return invoice
    if target == "POSTED" and (invoice.status != "DRAFT" or invoice.total <= 0):
        raise Conflict("Only a positive draft invoice can be posted.")
    if target == "VOID" and (invoice.paid or not reason.strip()):
        raise Conflict("Voiding needs a reason and no allocated payments.")
    invoice.status = target
    invoice.save(update_fields=["status", "updated_at"])
    record(organization, actor, f"billing.{target.lower()}", invoice, reason=reason)
    return invoice


@transaction.atomic
def allocate_payment(*, organization, actor, idempotency_key, paid_on, reference, allocations):
    authorize(organization, actor, FINANCE_ROLES)
    lock_organization(organization)
    if not allocations or len(allocations) > 100 or not reference.strip() or len(reference) > 120:
        raise ValidationError("A reference and 1–100 allocations are required.")
    normalized = sorted(
        [(str(x["invoice_id"]), number(x["amount"], positive=True, places=2)) for x in allocations]
    )
    if len({row[0] for row in normalized}) != len(normalized):
        raise ValidationError("Allocate to each invoice only once.")
    payload_hash = digest(
        dict(
            paid_on=paid_on,
            reference=reference,
            allocations=[(pk, format(value, ".2f")) for pk, value in normalized],
        )
    )
    previous = replay(Payment, organization, idempotency_key, payload_hash)
    if previous:
        return previous, False
    invoices = []
    signature = None
    for invoice_id, amount in normalized:
        invoice = (
            Invoice.objects.select_for_update()
            .filter(pk=invoice_id, organization=organization)
            .first()
        )
        if invoice is None or invoice.status != "POSTED":
            raise Conflict("Payments require posted invoices in this organization.")
        if paid_on < invoice.issued_on or amount > invoice.total - invoice.paid:
            raise Conflict("Payment date or allocation amount is invalid.")
        current = (invoice.partner_id, invoice.kind, invoice.currency)
        if signature and signature != current:
            raise Conflict("A payment cannot mix partners, directions or currencies.")
        signature = current
        invoices.append((invoice, amount))
    total = sum(amount for _, amount in invoices)
    if total >= Decimal("1000000000000000"):
        raise ValidationError("Payment amount exceeds the supported amount.")
    payment = Payment.objects.create(
        organization=organization,
        created_by=actor,
        partner_id=signature[0],
        kind=signature[1],
        currency=signature[2],
        amount=total,
        paid_on=paid_on,
        reference=reference,
        idempotency_key=idempotency_key,
        payload_hash=payload_hash,
    )
    for invoice, amount in invoices:
        PaymentAllocation.objects.create(
            organization=organization,
            created_by=actor,
            invoice=invoice,
            payment=payment,
            amount=amount,
        )
        invoice.paid += amount
        invoice.save(update_fields=["paid", "updated_at"])
    record(organization, actor, "billing.payment_allocated", payment, amount=str(total))
    return payment, True
