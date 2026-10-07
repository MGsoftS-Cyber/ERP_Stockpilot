# Generated for the StockPilot Week 2 catalog foundation.
import decimal
import uuid

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("tenancy", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Category",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("code", models.CharField(max_length=40)),
                ("name", models.CharField(max_length=120)),
                ("description", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "created_by",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="created_catalog_category_records", to=settings.AUTH_USER_MODEL),
                ),
                (
                    "organization",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="catalog_category_records", to="tenancy.organization"),
                ),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="TaxRate",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=80)),
                (
                    "rate",
                    models.DecimalField(
                        decimal_places=2,
                        help_text="Percentage, for example 19.00 means 19%.",
                        max_digits=5,
                        validators=[django.core.validators.MinValueValidator(decimal.Decimal("0.00"))],
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                (
                    "created_by",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="created_catalog_taxrate_records", to=settings.AUTH_USER_MODEL),
                ),
                (
                    "organization",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="catalog_taxrate_records", to="tenancy.organization"),
                ),
            ],
            options={"ordering": ["rate", "name"]},
        ),
        migrations.CreateModel(
            name="UnitOfMeasure",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=80)),
                ("symbol", models.CharField(max_length=16)),
                ("allows_decimals", models.BooleanField(default=True)),
                (
                    "created_by",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="created_catalog_unitofmeasure_records", to=settings.AUTH_USER_MODEL),
                ),
                (
                    "organization",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="catalog_unitofmeasure_records", to="tenancy.organization"),
                ),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Product",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("sku", models.CharField(max_length=64)),
                ("name", models.CharField(max_length=180)),
                ("description", models.TextField(blank=True)),
                (
                    "purchase_price",
                    models.DecimalField(decimal_places=4, default=decimal.Decimal("0.0000"), max_digits=18, validators=[django.core.validators.MinValueValidator(decimal.Decimal("0"))]),
                ),
                (
                    "selling_price",
                    models.DecimalField(decimal_places=4, default=decimal.Decimal("0.0000"), max_digits=18, validators=[django.core.validators.MinValueValidator(decimal.Decimal("0"))]),
                ),
                (
                    "minimum_stock",
                    models.DecimalField(decimal_places=4, default=decimal.Decimal("0.0000"), max_digits=18, validators=[django.core.validators.MinValueValidator(decimal.Decimal("0"))]),
                ),
                ("is_active", models.BooleanField(default=True)),
                (
                    "category",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="products", to="catalog.category"),
                ),
                (
                    "created_by",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="created_catalog_product_records", to=settings.AUTH_USER_MODEL),
                ),
                (
                    "organization",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="catalog_product_records", to="tenancy.organization"),
                ),
                (
                    "tax_rate",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="products", to="catalog.taxrate"),
                ),
                (
                    "unit",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="products", to="catalog.unitofmeasure"),
                ),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.AddConstraint(
            model_name="category",
            constraint=models.UniqueConstraint(fields=("organization", "code"), name="unique_category_code_per_organization"),
        ),
        migrations.AddConstraint(
            model_name="taxrate",
            constraint=models.UniqueConstraint(fields=("organization", "name"), name="unique_tax_name_per_organization"),
        ),
        migrations.AddConstraint(
            model_name="unitofmeasure",
            constraint=models.UniqueConstraint(fields=("organization", "symbol"), name="unique_unit_symbol_per_organization"),
        ),
        migrations.AddConstraint(
            model_name="product",
            constraint=models.UniqueConstraint(fields=("organization", "sku"), name="unique_product_sku_per_organization"),
        ),
    ]

