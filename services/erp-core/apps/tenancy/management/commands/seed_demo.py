# Teaching edition: Create repeatable example data and one opening stock posting.
import uuid
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog.models import Category, Product, TaxRate, UnitOfMeasure
from apps.inventory.models import StockAdjustment, Warehouse
from apps.inventory.services import post_stock_adjustment
from apps.partners.models import BusinessPartner
from apps.tenancy.models import Membership, Organization, User


class Command(BaseCommand):
    help = (
        "Create demo accounts, organizations, catalog records and opening stock for local testing."
    )

    # Run the command against the currently configured database.
    @transaction.atomic
    def handle(self, *args, **options) -> None:
        admin, created = User.objects.get_or_create(
            email="admin@stockpilot.local",
            defaults={"first_name": "StockPilot", "last_name": "Admin", "is_staff": True},
        )
        if created or not admin.has_usable_password():
            admin.set_password("Admin123!")
            admin.save(update_fields=["password"])

        viewer, viewer_created = User.objects.get_or_create(
            email="viewer@stockpilot.local",
            defaults={"first_name": "Demo", "last_name": "Viewer"},
        )
        if viewer_created or not viewer.has_usable_password():
            viewer.set_password("Viewer123!")
            viewer.save(update_fields=["password"])

        organization, _ = Organization.objects.get_or_create(
            slug="stockpilot-demo",
            defaults={"name": "StockPilot Demo Company"},
        )
        Membership.objects.update_or_create(
            organization=organization,
            user=admin,
            defaults={"role": Membership.Role.ADMINISTRATOR, "is_active": True},
        )
        Membership.objects.update_or_create(
            organization=organization,
            user=viewer,
            defaults={"role": Membership.Role.VIEWER, "is_active": True},
        )

        unit, _ = UnitOfMeasure.objects.get_or_create(
            organization=organization,
            symbol="pcs",
            defaults={"name": "Pieces", "allows_decimals": False, "created_by": admin},
        )
        category, _ = Category.objects.get_or_create(
            organization=organization,
            code="ELEC",
            defaults={"name": "Electronics", "created_by": admin},
        )
        tax, _ = TaxRate.objects.get_or_create(
            organization=organization,
            name="VAT 19",
            defaults={"rate": Decimal("19.00"), "created_by": admin},
        )
        warehouse, _ = Warehouse.objects.get_or_create(
            organization=organization,
            code="MAIN",
            defaults={"name": "Main Warehouse", "created_by": admin},
        )
        BusinessPartner.objects.get_or_create(
            organization=organization,
            code="SUP-001",
            defaults={
                "name": "Demo Supplier",
                "partner_type": BusinessPartner.PartnerType.SUPPLIER,
                "email": "supplier@example.com",
                "created_by": admin,
            },
        )
        BusinessPartner.objects.get_or_create(
            organization=organization,
            code="CUS-001",
            defaults={
                "name": "Demo Customer",
                "partner_type": BusinessPartner.PartnerType.CUSTOMER,
                "email": "customer@example.com",
                "created_by": admin,
            },
        )
        product, _ = Product.objects.get_or_create(
            organization=organization,
            sku="MOUSE-001",
            defaults={
                "name": "Wireless Mouse",
                "category": category,
                "unit": unit,
                "tax_rate": tax,
                "purchase_price": Decimal("20.0000"),
                "selling_price": Decimal("35.0000"),
                "minimum_stock": Decimal("5.0000"),
                "created_by": admin,
            },
        )

        opening_key = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"stockpilot:demo:opening:{organization.id}",
        )
        if not StockAdjustment.objects.filter(
            organization=organization,
            idempotency_key=opening_key,
        ).exists():
            post_stock_adjustment(
                organization=organization,
                actor=admin,
                warehouse=warehouse,
                reference="ADJ-DEMO-OPENING",
                reason="Deterministic Week 3 opening demonstration stock",
                idempotency_key=opening_key,
                lines=[
                    {
                        "product": product,
                        "quantity_signed": Decimal("25.0000"),
                        "unit_cost": product.purchase_price,
                    }
                ],
            )

        self.stdout.write(self.style.SUCCESS("StockPilot demo data is ready."))
        self.stdout.write(f"Organization ID: {organization.id}")
        self.stdout.write("Admin: admin@stockpilot.local / Admin123!")
        self.stdout.write("Viewer: viewer@stockpilot.local / Viewer123!")
