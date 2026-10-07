"""Read-side totals: separate currencies and explain precisely what is measured."""

from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from apps.billing.models import Invoice, Payment

from .models import Expense


def total(queryset, field):
    return queryset.aggregate(value=Sum(field))["value"] or Decimal(0)


def summary(organization, currency):
    invoices = Invoice.objects.filter(organization=organization, currency=currency, status="POSTED")
    sales = invoices.filter(kind="CUSTOMER")
    suppliers = invoices.filter(kind="SUPPLIER")
    payments = Payment.objects.filter(organization=organization, currency=currency)
    expenses = total(
        Expense.objects.filter(organization=organization, currency=currency, is_void=False),
        "amount",
    )
    revenue = total(sales, "subtotal")  # Excludes VAT/tax; based on posted invoices, not cash.
    cost = total(
        sales, "cost_total"
    )  # Operational cost snapshot, not statutory inventory valuation.
    cash_in = total(payments.filter(kind="CUSTOMER"), "amount")
    cash_out = total(payments.filter(kind="SUPPLIER"), "amount")
    overdue = sales.filter(due_on__lt=timezone.localdate())
    values = dict(
        revenue=revenue,
        cost=cost,
        gross_margin=revenue - cost,
        expenses=expenses,
        operational_result=revenue - cost - expenses,
        receivables=total(sales, "total") - total(sales, "paid"),
        payables=total(suppliers, "total") - total(suppliers, "paid"),
        overdue_receivables=total(overdue, "total") - total(overdue, "paid"),
        cash_in=cash_in,
        cash_out=cash_out,
        net_cash_flow=cash_in - cash_out - expenses,
    )
    return {"currency": currency, **{key: format(value, ".2f") for key, value in values.items()}}
