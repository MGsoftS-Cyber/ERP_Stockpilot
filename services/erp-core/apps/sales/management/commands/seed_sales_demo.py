from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog.models import Product
from apps.inventory.models import Warehouse
from apps.partners.models import BusinessPartner
from apps.sales.models import SalesOrder
from apps.sales.services import save_draft
from apps.tenancy.models import Organization, User


class Command(BaseCommand):
    help = "Create sales demonstration data without reserving or shipping stock."

    @transaction.atomic
    def handle(self, *args, **options):
        # Reuse earlier deterministic seeds so repeatedly seeding does not add stock.
        call_command("seed_purchasing_demo")
        organization = Organization.objects.select_for_update().get(slug="stockpilot-demo")
        # Rename the historical demo marker without creating a duplicate draft.
        SalesOrder.objects.filter(organization=organization, notes="WEEK5_DEMO").update(
            notes="SALES_DEMO"
        )
        if not SalesOrder.objects.filter(organization=organization, notes="SALES_DEMO").exists():
            product = Product.objects.get(organization=organization, sku="MOUSE-001")
            save_draft(
                organization=organization,
                actor=User.objects.get(email="admin@stockpilot.local"),
                customer=BusinessPartner.objects.get(organization=organization, code="CUS-001"),
                warehouse=Warehouse.objects.filter(organization=organization)
                .order_by("code")
                .first(),
                notes="SALES_DEMO",
                lines=[{"product": product, "quantity": "10", "unit_price": "35"}],
            )
        self.stdout.write(self.style.SUCCESS("Sales draft is ready. No goods were shipped."))
