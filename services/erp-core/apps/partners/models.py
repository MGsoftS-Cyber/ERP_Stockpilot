# Teaching edition: Model database records, relationships and constraints.
from django.db import models

from apps.common.models import OrganizationScopedModel


class BusinessPartner(OrganizationScopedModel):
    class PartnerType(models.TextChoices):
        CUSTOMER = "CUSTOMER", "Customer"
        SUPPLIER = "SUPPLIER", "Supplier"
        BOTH = "BOTH", "Customer and supplier"

    # Text field: max_length limits length; choices supplies permitted values.
    code = models.CharField(max_length=40)
    # Text field: max_length limits length; choices supplies permitted values.
    name = models.CharField(max_length=180)
    # Text field: max_length limits length; choices supplies permitted values.
    partner_type = models.CharField(max_length=16, choices=PartnerType.choices)
    # Email-shaped text; account creation and uniqueness are separate rules.
    email = models.EmailField(blank=True)
    # Text field: max_length limits length; choices supplies permitted values.
    phone = models.CharField(max_length=40, blank=True)
    # Long text; validate its business meaning in the input/service contract.
    address = models.TextField(blank=True)
    # Text field: max_length limits length; choices supplies permitted values.
    tax_identifier = models.CharField(max_length=80, blank=True)
    # True/False flag; default is used when creating without a value.
    is_active = models.BooleanField(default=True)

    # Django metadata: schema or API options, not a constructor.
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
