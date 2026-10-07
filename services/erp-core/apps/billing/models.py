"""Billing records: posted amounts are fixed; allocations link payments to invoices."""

from django.db import models
from django.db.models import F, Q

from apps.common.models import OrganizationScopedModel


class Invoice(OrganizationScopedModel):
    class Kind(models.TextChoices):
        CUSTOMER = "CUSTOMER", "Customer receivable"
        SUPPLIER = "SUPPLIER", "Supplier payable"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        POSTED = "POSTED", "Posted"
        VOID = "VOID", "Voided"

    partner = models.ForeignKey("partners.BusinessPartner", on_delete=models.PROTECT)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    reference = models.CharField(max_length=64)
    currency = models.CharField(max_length=3, default="DZD")
    issued_on = models.DateField()
    due_on = models.DateField()
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.DRAFT)
    # A whole-order snapshot can be invoiced once. Manual invoices are also supported.
    sales_order = models.OneToOneField("sales.SalesOrder", on_delete=models.PROTECT, null=True)
    purchase_order = models.OneToOneField(
        "purchasing.PurchaseOrder", on_delete=models.PROTECT, null=True
    )
    subtotal = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    tax_total = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    paid = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    cost_total = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    idempotency_key = models.UUIDField()
    payload_hash = models.CharField(max_length=64)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "idempotency_key"], name="invoice_key"),
            models.UniqueConstraint(
                fields=["organization", "kind", "partner", "reference"], name="invoice_reference"
            ),
            models.CheckConstraint(
                condition=Q(paid__gte=0, paid__lte=F("total")), name="invoice_paid_bounds"
            ),
            models.CheckConstraint(condition=Q(total__gte=0), name="invoice_total_nonnegative"),
            models.CheckConstraint(
                condition=Q(due_on__gte=F("issued_on")), name="invoice_due_date"
            ),
        ]


class InvoiceLine(OrganizationScopedModel):
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="lines")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, null=True)
    description = models.CharField(max_length=240)
    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    unit_price = models.DecimalField(max_digits=18, decimal_places=4)
    unit_cost = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    net = models.DecimalField(max_digits=18, decimal_places=2)
    tax = models.DecimalField(max_digits=18, decimal_places=2)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="invoice_line_qty"),
            models.CheckConstraint(
                condition=Q(unit_price__gte=0, unit_cost__gte=0), name="invoice_line_prices"
            ),
            models.CheckConstraint(
                condition=Q(tax_rate__gte=0, tax_rate__lte=100), name="invoice_line_tax"
            ),
        ]


class Payment(OrganizationScopedModel):
    # A payment can settle several invoices, but only for one partner/currency/direction.
    partner = models.ForeignKey("partners.BusinessPartner", on_delete=models.PROTECT)
    kind = models.CharField(max_length=16, choices=Invoice.Kind.choices)
    currency = models.CharField(max_length=3)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    paid_on = models.DateField()
    reference = models.CharField(max_length=120)
    idempotency_key = models.UUIDField()
    payload_hash = models.CharField(max_length=64)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "idempotency_key"], name="payment_key"),
            models.CheckConstraint(condition=Q(amount__gt=0), name="payment_positive"),
        ]


class PaymentAllocation(OrganizationScopedModel):
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name="allocations")
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="allocations")
    amount = models.DecimalField(max_digits=18, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["payment", "invoice"], name="allocation_once"),
            models.CheckConstraint(condition=Q(amount__gt=0), name="allocation_positive"),
        ]
