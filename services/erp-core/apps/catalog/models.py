# Model database records, relationships and constraints.
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from apps.common.models import OrganizationScopedModel


class Category(OrganizationScopedModel):
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "code"],
                name="unique_category_code_per_organization",
            )
        ]

    # Return a readable label for admin and debugging without modifying data.
    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class UnitOfMeasure(OrganizationScopedModel):
    name = models.CharField(max_length=80)
    symbol = models.CharField(max_length=16)
    allows_decimals = models.BooleanField(default=True)
    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "symbol"],
                name="unique_unit_symbol_per_organization",
            )
        ]

    # Return a readable label for admin and debugging without modifying data.
    def __str__(self) -> str:
        return self.symbol


class TaxRate(OrganizationScopedModel):
    name = models.CharField(max_length=80)
    rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Percentage, for example 19.00 means 19%.",
    )
    is_active = models.BooleanField(default=True)
    class Meta:
        ordering = ["rate", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"],
                name="unique_tax_name_per_organization",
            )
        ]

    # Return a readable label for admin and debugging without modifying data.
    def __str__(self) -> str:
        return f"{self.name} ({self.rate}%)"


class Product(OrganizationScopedModel):
    sku = models.CharField(max_length=64)
    name = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
        null=True,
        blank=True,
    )
    unit = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT, related_name="products")
    tax_rate = models.ForeignKey(
        TaxRate,
        on_delete=models.PROTECT,
        related_name="products",
        null=True,
        blank=True,
    )
    purchase_price = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal("0.0000"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    selling_price = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal("0.0000"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    minimum_stock = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal("0.0000"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    is_active = models.BooleanField(default=True)
    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "sku"],
                name="unique_product_sku_per_organization",
            )
        ]

    # Validate model relationships; save() does not automatically call full_clean().
    def clean(self) -> None:
        super().clean()
        related_objects = {
            "category": self.category,
            "unit": self.unit,
            "tax_rate": self.tax_rate,
        }
        errors = {}
        for field, related in related_objects.items():
            if related is not None and related.organization_id != self.organization_id:
                errors[field] = "The related record must belong to the same organization."
        if errors:
            raise ValidationError(errors)

    # Return a readable label for admin and debugging without modifying data.
    def __str__(self) -> str:
        return f"{self.sku} - {self.name}"
