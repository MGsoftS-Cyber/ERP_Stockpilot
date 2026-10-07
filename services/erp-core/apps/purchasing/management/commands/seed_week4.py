# Teaching edition: Reuse the baseline seed and add one draft purchase order.
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog.models import Product
from apps.partners.models import BusinessPartner
from apps.purchasing.models import PurchaseOrder
from apps.purchasing.services import create_order
from apps.tenancy.models import Organization, User


class Command(BaseCommand):
    help = "Create catalog and opening stock, then add a purchase draft without receiving goods."

    # Run the command against the currently configured database.
    @transaction.atomic
    def handle(self, *args, **options):
        call_command("seed_demo")
        organization = Organization.objects.select_for_update().get(slug="stockpilot-demo")
        if not PurchaseOrder.objects.filter(organization=organization, notes="WEEK4_DEMO").exists():
            create_order(
                organization=organization,
                actor=User.objects.get(email="admin@stockpilot.local"),
                supplier=BusinessPartner.objects.get(organization=organization, code="SUP-001"),
                notes="WEEK4_DEMO",
                lines=[
                    {
                        "product": Product.objects.get(organization=organization, sku="MOUSE-001"),
                        "quantity": "10",
                        "unit_price": "20",
                    }
                ],
            )
        self.stdout.write(
            self.style.SUCCESS(
                "Purchase draft ready. Review and approve it before recording goods receipts."
            )
        )
