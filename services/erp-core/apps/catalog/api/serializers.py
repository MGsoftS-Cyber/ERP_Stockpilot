# Teaching edition: Convert records to JSON and validate incoming API values.
from rest_framework import serializers

from apps.catalog.models import Category, Product, TaxRate, UnitOfMeasure


class CategorySerializer(serializers.ModelSerializer):
    # Django metadata: schema or API options, not a constructor.
    class Meta:
        model = Category
        fields = ["id", "code", "name", "description", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class UnitOfMeasureSerializer(serializers.ModelSerializer):
    # Django metadata: schema or API options, not a constructor.
    class Meta:
        model = UnitOfMeasure
        fields = ["id", "name", "symbol", "allows_decimals", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class TaxRateSerializer(serializers.ModelSerializer):
    # Django metadata: schema or API options, not a constructor.
    class Meta:
        model = TaxRate
        fields = ["id", "name", "rate", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    unit_symbol = serializers.CharField(source="unit.symbol", read_only=True)
    tax_rate_value = serializers.DecimalField(
        source="tax_rate.rate",
        max_digits=5,
        decimal_places=2,
        read_only=True,
    )

    # Django metadata: schema or API options, not a constructor.
    class Meta:
        model = Product
        fields = [
            "id",
            "sku",
            "name",
            "description",
            "category",
            "category_name",
            "unit",
            "unit_symbol",
            "tax_rate",
            "tax_rate_value",
            "purchase_price",
            "selling_price",
            "minimum_stock",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    # Reject invalid input combinations before saving or calling services.
    def validate(self, attrs):
        request = self.context["request"]
        organization = request.organization
        errors = {}
        for field in ("category", "unit", "tax_rate"):
            related = attrs.get(field, getattr(self.instance, field, None))
            if related is not None and related.organization_id != organization.id:
                errors[field] = "Must belong to the selected organization."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs
