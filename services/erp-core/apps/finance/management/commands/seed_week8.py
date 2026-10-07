"""Repeatable demo seed. OCR and forecasts still use the real service on demand."""

import uuid
from datetime import date

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.billing.services import allocate_payment, change_status, create_invoice
from apps.catalog.models import Product
from apps.finance.services import create_expense
from apps.partners.models import BusinessPartner
from apps.tenancy.models import Organization, User


class Command(BaseCommand):
    help = "Create a complete local ERP demo with a sample invoice, payment and cash expense."

    @transaction.atomic
    def handle(self, *args, **options):
        call_command("seed_week5")
        organization = Organization.objects.get(slug="stockpilot-demo")
        args = dict(
            organization=organization, actor=User.objects.get(email="admin@stockpilot.local")
        )
        product = Product.objects.get(organization=organization, sku="MOUSE-001")
        customer = BusinessPartner.objects.get(organization=organization, code="CUS-001")
        key = lambda value: uuid.uuid5(organization.pk, f"week8-demo-{value}")  # noqa: E731
        # Fixed dates/keys keep the seed repeatable on a different day.
        invoice, created = create_invoice(
            **args,
            idempotency_key=key("invoice"),
            kind="CUSTOMER",
            partner_id=customer.pk,
            reference="DEMO-W8-001",
            currency="DZD",
            issued_on=date(2026, 1, 15),
            due_on=date(2026, 2, 15),
            lines=[
                dict(
                    product_id=product.pk,
                    description="Demo mouse",
                    quantity="10",
                    unit_price="35",
                    unit_cost="20",
                    tax_rate="19",
                )
            ],
        )
        if created:
            change_status(**args, invoice_id=invoice.pk, target="POSTED")
            allocate_payment(
                **args,
                idempotency_key=key("payment"),
                paid_on=date(2026, 1, 20),
                reference="DEMO-PAY-001",
                allocations=[dict(invoice_id=invoice.pk, amount="100")],
            )
            create_expense(
                **args,
                idempotency_key=key("expense"),
                description="Demo packing supplies",
                category="Packaging",
                amount="25",
                currency="DZD",
                spent_on=date(2026, 1, 20),
            )
        self.stdout.write(
            self.style.SUCCESS(
                "ERP demo ready. Explore finance and audit records; "
                "upload invoices or run forecasts from the AI review screen."
            )
        )
