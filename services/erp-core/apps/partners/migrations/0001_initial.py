# Generated for the StockPilot Week 2 partner foundation.
import uuid

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
            name="BusinessPartner",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("code", models.CharField(max_length=40)),
                ("name", models.CharField(max_length=180)),
                (
                    "partner_type",
                    models.CharField(
                        choices=[("CUSTOMER", "Customer"), ("SUPPLIER", "Supplier"), ("BOTH", "Customer and supplier")],
                        max_length=16,
                    ),
                ),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("phone", models.CharField(blank=True, max_length=40)),
                ("address", models.TextField(blank=True)),
                ("tax_identifier", models.CharField(blank=True, max_length=80)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "created_by",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="created_partners_businesspartner_records", to=settings.AUTH_USER_MODEL),
                ),
                (
                    "organization",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="partners_businesspartner_records", to="tenancy.organization"),
                ),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.AddConstraint(
            model_name="businesspartner",
            constraint=models.UniqueConstraint(fields=("organization", "code"), name="unique_partner_code_per_organization"),
        ),
    ]

