"""Currency-separated operational totals using three bounded aggregate queries."""

from decimal import Decimal

from django.db.models import Q, Sum
from django.utils import timezone

from apps.billing.models import Invoice, Payment
from apps.tenancy.models import Organization

from .models import Expense


def summary(organization: Organization, currency: str) -> dict[str, str]:
    sales = Q(kind="CUSTOMER")
    suppliers = Q(kind="SUPPLIER")
    overdue = sales & Q(due_on__lt=timezone.localdate())
    invoices = Invoice.objects.filter(
        organization=organization, currency=currency, status="POSTED"
    ).aggregate(
        revenue=Sum("subtotal", filter=sales),
        cost=Sum("cost_total", filter=sales),
        customer_total=Sum("total", filter=sales),
        customer_paid=Sum("paid", filter=sales),
        supplier_total=Sum("total", filter=suppliers),
        supplier_paid=Sum("paid", filter=suppliers),
        overdue_total=Sum("total", filter=overdue),
        overdue_paid=Sum("paid", filter=overdue),
    )
    payments = Payment.objects.filter(organization=organization, currency=currency).aggregate(
        cash_in=Sum("amount", filter=sales), cash_out=Sum("amount", filter=suppliers)
    )
    expenses = Expense.objects.filter(
        organization=organization, currency=currency, is_void=False
    ).aggregate(amount=Sum("amount"))["amount"] or Decimal(0)
    invoices = {key: value or Decimal(0) for key, value in invoices.items()}
    payments = {key: value or Decimal(0) for key, value in payments.items()}
    revenue, cost = invoices["revenue"], invoices["cost"]
    values = dict(
        revenue=revenue,
        cost=cost,
        gross_margin=revenue - cost,
        expenses=expenses,
        operational_result=revenue - cost - expenses,
        receivables=invoices["customer_total"] - invoices["customer_paid"],
        payables=invoices["supplier_total"] - invoices["supplier_paid"],
        overdue_receivables=invoices["overdue_total"] - invoices["overdue_paid"],
        **payments,
        net_cash_flow=payments["cash_in"] - payments["cash_out"] - expenses,
    )
    return {"currency": currency, **{key: format(value, ".2f") for key, value in values.items()}}
