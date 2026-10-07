# StockPilot Week 3: immutable inventory ledger and command documents.
import decimal
import uuid

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("catalog", "0001_initial"),
        ("inventory", "0001_initial"),
        ("tenancy", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="StockAdjustment",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("reference", models.CharField(max_length=64)),
                ("reason", models.TextField()),
                ("idempotency_key", models.UUIDField()),
                ("posted_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "created_by",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="created_inventory_stockadjustment_records", to=settings.AUTH_USER_MODEL),
                ),
                (
                    "organization",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="inventory_stockadjustment_records", to="tenancy.organization"),
                ),
                (
                    "warehouse",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="stock_adjustments", to="inventory.warehouse"),
                ),
            ],
            options={"ordering": ["-posted_at"]},
        ),
        migrations.CreateModel(
            name="StockTransfer",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("reference", models.CharField(max_length=64)),
                ("reason", models.TextField(blank=True)),
                ("idempotency_key", models.UUIDField()),
                ("transferred_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "created_by",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="created_inventory_stocktransfer_records", to=settings.AUTH_USER_MODEL),
                ),
                (
                    "destination_warehouse",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="incoming_stock_transfers", to="inventory.warehouse"),
                ),
                (
                    "organization",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="inventory_stocktransfer_records", to="tenancy.organization"),
                ),
                (
                    "source_warehouse",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="outgoing_stock_transfers", to="inventory.warehouse"),
                ),
            ],
            options={"ordering": ["-transferred_at"]},
        ),
        migrations.CreateModel(
            name="StockBalance",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("on_hand", models.DecimalField(decimal_places=4, default=decimal.Decimal("0"), max_digits=18)),
                ("reserved", models.DecimalField(decimal_places=4, default=decimal.Decimal("0"), max_digits=18)),
                (
                    "created_by",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="created_inventory_stockbalance_records", to=settings.AUTH_USER_MODEL),
                ),
                (
                    "organization",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="inventory_stockbalance_records", to="tenancy.organization"),
                ),
                (
                    "product",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="stock_balances", to="catalog.product"),
                ),
                (
                    "warehouse",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="stock_balances", to="inventory.warehouse"),
                ),
            ],
            options={"ordering": ["product__name", "warehouse__name"]},
        ),
        migrations.CreateModel(
            name="StockMovement",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "movement_type",
                    models.CharField(
                        choices=[
                            ("OPENING", "Opening balance"),
                            ("PURCHASE_RECEIPT", "Purchase receipt"),
                            ("SALE_SHIPMENT", "Sale shipment"),
                            ("CUSTOMER_RETURN", "Customer return"),
                            ("SUPPLIER_RETURN", "Supplier return"),
                            ("ADJUSTMENT_IN", "Adjustment in"),
                            ("ADJUSTMENT_OUT", "Adjustment out"),
                            ("TRANSFER_IN", "Transfer in"),
                            ("TRANSFER_OUT", "Transfer out"),
                        ],
                        max_length=32,
                    ),
                ),
                ("quantity_signed", models.DecimalField(decimal_places=4, max_digits=18)),
                (
                    "unit_cost",
                    models.DecimalField(
                        decimal_places=4,
                        default=decimal.Decimal("0.0000"),
                        max_digits=18,
                        validators=[django.core.validators.MinValueValidator(decimal.Decimal("0"))],
                    ),
                ),
                ("occurred_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "source_type",
                    models.CharField(
                        choices=[
                            ("STOCK_ADJUSTMENT", "Stock adjustment"),
                            ("STOCK_TRANSFER", "Stock transfer"),
                            ("PURCHASE_RECEIPT", "Purchase receipt"),
                            ("SHIPMENT", "Shipment"),
                            ("CUSTOMER_RETURN", "Customer return"),
                            ("SUPPLIER_RETURN", "Supplier return"),
                        ],
                        max_length=32,
                    ),
                ),
                ("source_id", models.UUIDField()),
                ("idempotency_key", models.UUIDField(unique=True)),
                (
                    "created_by",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="created_inventory_stockmovement_records", to=settings.AUTH_USER_MODEL),
                ),
                (
                    "organization",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="inventory_stockmovement_records", to="tenancy.organization"),
                ),
                (
                    "product",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="stock_movements", to="catalog.product"),
                ),
                (
                    "warehouse",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="stock_movements", to="inventory.warehouse"),
                ),
            ],
            options={
                "ordering": ["-occurred_at", "-created_at"],
                "indexes": [
                    models.Index(fields=["organization", "product", "warehouse", "occurred_at"], name="movement_stock_history_idx"),
                    models.Index(fields=["organization", "source_type", "source_id"], name="movement_source_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="StockReservation",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "quantity",
                    models.DecimalField(
                        decimal_places=4,
                        max_digits=18,
                        validators=[django.core.validators.MinValueValidator(decimal.Decimal("0.0001"))],
                    ),
                ),
                (
                    "source_type",
                    models.CharField(
                        choices=[("MANUAL", "Manual"), ("SALES_ORDER", "Sales order"), ("OTHER", "Other")],
                        max_length=32,
                    ),
                ),
                ("source_id", models.UUIDField()),
                (
                    "status",
                    models.CharField(choices=[("ACTIVE", "Active"), ("RELEASED", "Released")], default="ACTIVE", max_length=16),
                ),
                ("idempotency_key", models.UUIDField()),
                ("released_at", models.DateTimeField(blank=True, null=True)),
                (
                    "created_by",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="created_inventory_stockreservation_records", to=settings.AUTH_USER_MODEL),
                ),
                (
                    "organization",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="inventory_stockreservation_records", to="tenancy.organization"),
                ),
                (
                    "product",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="stock_reservations", to="catalog.product"),
                ),
                (
                    "warehouse",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="stock_reservations", to="inventory.warehouse"),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="StockAdjustmentLine",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("quantity_signed", models.DecimalField(decimal_places=4, max_digits=18)),
                (
                    "unit_cost",
                    models.DecimalField(
                        decimal_places=4,
                        default=decimal.Decimal("0.0000"),
                        max_digits=18,
                        validators=[django.core.validators.MinValueValidator(decimal.Decimal("0"))],
                    ),
                ),
                (
                    "adjustment",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="lines", to="inventory.stockadjustment"),
                ),
                (
                    "created_by",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="created_inventory_stockadjustmentline_records", to=settings.AUTH_USER_MODEL),
                ),
                (
                    "organization",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="inventory_stockadjustmentline_records", to="tenancy.organization"),
                ),
                (
                    "product",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="stock_adjustment_lines", to="catalog.product"),
                ),
            ],
            options={"ordering": ["created_at"]},
        ),
        migrations.CreateModel(
            name="StockTransferLine",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "quantity",
                    models.DecimalField(
                        decimal_places=4,
                        max_digits=18,
                        validators=[django.core.validators.MinValueValidator(decimal.Decimal("0.0001"))],
                    ),
                ),
                (
                    "unit_cost",
                    models.DecimalField(
                        decimal_places=4,
                        default=decimal.Decimal("0.0000"),
                        max_digits=18,
                        validators=[django.core.validators.MinValueValidator(decimal.Decimal("0"))],
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="created_inventory_stocktransferline_records", to=settings.AUTH_USER_MODEL),
                ),
                (
                    "organization",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="inventory_stocktransferline_records", to="tenancy.organization"),
                ),
                (
                    "product",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="stock_transfer_lines", to="catalog.product"),
                ),
                (
                    "transfer",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="lines", to="inventory.stocktransfer"),
                ),
            ],
            options={"ordering": ["created_at"]},
        ),
        migrations.AddConstraint(
            model_name="stockadjustment",
            constraint=models.UniqueConstraint(fields=("organization", "reference"), name="unique_adjustment_reference_per_organization"),
        ),
        migrations.AddConstraint(
            model_name="stockadjustment",
            constraint=models.UniqueConstraint(fields=("organization", "idempotency_key"), name="unique_adjustment_idempotency_per_organization"),
        ),
        migrations.AddConstraint(
            model_name="stocktransfer",
            constraint=models.UniqueConstraint(fields=("organization", "reference"), name="unique_transfer_reference_per_organization"),
        ),
        migrations.AddConstraint(
            model_name="stocktransfer",
            constraint=models.UniqueConstraint(fields=("organization", "idempotency_key"), name="unique_transfer_idempotency_per_organization"),
        ),
        migrations.AddConstraint(
            model_name="stocktransfer",
            constraint=models.CheckConstraint(condition=~models.Q(source_warehouse=models.F("destination_warehouse")), name="transfer_warehouses_are_different"),
        ),
        migrations.AddConstraint(
            model_name="stockbalance",
            constraint=models.UniqueConstraint(fields=("organization", "product", "warehouse"), name="unique_product_warehouse_balance"),
        ),
        migrations.AddConstraint(
            model_name="stockbalance",
            constraint=models.CheckConstraint(condition=models.Q(on_hand__gte=0), name="stock_balance_on_hand_is_not_negative"),
        ),
        migrations.AddConstraint(
            model_name="stockbalance",
            constraint=models.CheckConstraint(condition=models.Q(reserved__gte=0), name="stock_balance_reserved_is_not_negative"),
        ),
        migrations.AddConstraint(
            model_name="stockbalance",
            constraint=models.CheckConstraint(condition=models.Q(reserved__lte=models.F("on_hand")), name="stock_balance_reserved_not_above_on_hand"),
        ),
        migrations.AddConstraint(
            model_name="stockmovement",
            constraint=models.CheckConstraint(condition=~models.Q(quantity_signed=0), name="stock_movement_quantity_is_not_zero"),
        ),
        migrations.AddConstraint(
            model_name="stockmovement",
            constraint=models.CheckConstraint(condition=models.Q(unit_cost__gte=0), name="movement_unit_cost_not_negative"),
        ),
        migrations.AddConstraint(
            model_name="stockreservation",
            constraint=models.UniqueConstraint(fields=("organization", "idempotency_key"), name="unique_reservation_idempotency_per_organization"),
        ),
        migrations.AddConstraint(
            model_name="stockreservation",
            constraint=models.CheckConstraint(condition=models.Q(quantity__gt=0), name="reservation_quantity_is_positive"),
        ),
        migrations.AddConstraint(
            model_name="stockadjustmentline",
            constraint=models.UniqueConstraint(fields=("adjustment", "product"), name="one_adjustment_line_per_product"),
        ),
        migrations.AddConstraint(
            model_name="stockadjustmentline",
            constraint=models.CheckConstraint(condition=~models.Q(quantity_signed=0), name="adjustment_quantity_is_not_zero"),
        ),
        migrations.AddConstraint(
            model_name="stockadjustmentline",
            constraint=models.CheckConstraint(condition=models.Q(unit_cost__gte=0), name="adjustment_unit_cost_not_negative"),
        ),
        migrations.AddConstraint(
            model_name="stocktransferline",
            constraint=models.UniqueConstraint(fields=("transfer", "product"), name="one_transfer_line_per_product"),
        ),
        migrations.AddConstraint(
            model_name="stocktransferline",
            constraint=models.CheckConstraint(condition=models.Q(quantity__gt=0), name="transfer_quantity_is_positive"),
        ),
        migrations.AddConstraint(
            model_name="stocktransferline",
            constraint=models.CheckConstraint(condition=models.Q(unit_cost__gte=0), name="transfer_unit_cost_not_negative"),
        ),
    ]
