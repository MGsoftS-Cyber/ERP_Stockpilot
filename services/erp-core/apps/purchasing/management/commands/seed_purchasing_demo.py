# Reuse the baseline seed and add one draft purchase order.
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog.models import Product
from apps.partners.models import BusinessPartner
from apps.purchasing.models import PurchaseOrder
from apps.purchasing.services import create_order
from apps.tenancy.models import Organization, User


class Command(BaseCommand):
    help = "Create purchasing demonstration data without posting receipts."

    # Run the command against the currently configured database.
    @transaction.atomic
    def handle(self, *args, **options):
        call_command("seed_demo")
        organization = Organization.objects.select_for_update().get(slug="stockpilot-demo")
        # Rename the historical demo marker without creating a duplicate draft.
        PurchaseOrder.objects.filter(organization=organization, notes="WEEK4_DEMO").update(
            notes="PURCHASING_DEMO"
        )
        if not PurchaseOrder.objects.filter(
            organization=organization, notes="PURCHASING_DEMO"
        ).exists():
            create_order(
                organization=organization,
                actor=User.objects.get(email="admin@stockpilot.local"),
                supplier=BusinessPartner.objects.get(organization=organization, code="SUP-001"),
                notes="PURCHASING_DEMO",
                lines=[
                    {
                        "product": Product.objects.get(organization=organization, sku="MOUSE-001"),
                        "quantity": "10",
                        "unit_price": "20",
                    }
                ],
            )
        self.stdout.write(self.style.SUCCESS("Purchase draft is ready in Purchasing."))
