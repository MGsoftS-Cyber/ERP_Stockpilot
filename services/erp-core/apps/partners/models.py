# Model database records, relationships and constraints.
from django.db import models

from apps.common.models import OrganizationScopedModel


class BusinessPartner(OrganizationScopedModel):
    class PartnerType(models.TextChoices):
        CUSTOMER = "CUSTOMER", "Customer"
        SUPPLIER = "SUPPLIER", "Supplier"
        BOTH = "BOTH", "Customer and supplier"
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=180)
    partner_type = models.CharField(max_length=16, choices=PartnerType.choices)
    # Email-shaped text; account creation and uniqueness are separate rules.
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    address = models.TextField(blank=True)
    tax_identifier = models.CharField(max_length=80, blank=True)
    is_active = models.BooleanField(default=True)
    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "code"],
                name="unique_partner_code_per_organization",
            )
        ]

    # Return a readable label for admin and debugging without modifying data.
    def __str__(self) -> str:
        return f"{self.code} - {self.name}"
