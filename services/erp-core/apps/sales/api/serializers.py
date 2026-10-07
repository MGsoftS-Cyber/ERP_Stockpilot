"""Validate incoming JSON and expose read-only sales documents to React."""

from decimal import Decimal

from drf_spectacular.utils import extend_schema_serializer
from rest_framework import serializers

from apps.catalog.models import Product
from apps.inventory.models import Warehouse
from apps.partners.models import BusinessPartner
from apps.sales.models import (
    CustomerReturn,
    CustomerReturnLine,
    SalesOrder,
    SalesOrderLine,
    Shipment,
    ShipmentLine,
)
from apps.tenancy.services import get_request_membership


@extend_schema_serializer(component_name="SalesLineInput")
class LineInput(serializers.Serializer):
    product = serializers.UUIDField()
    quantity = serializers.DecimalField(
        max_digits=18, decimal_places=4, min_value=Decimal("0.0001")
    )
    unit_price = serializers.DecimalField(max_digits=18, decimal_places=4, min_value=Decimal("0"))


@extend_schema_serializer(component_name="SalesDraftInput")
class DraftInput(serializers.Serializer):
    customer = serializers.PrimaryKeyRelatedField(queryset=BusinessPartner.objects.all())
    warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.all())
    notes = serializers.CharField(required=False, allow_blank=True)
    lines = LineInput(many=True, allow_empty=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request:
            organization = get_request_membership(request).organization
            # Cross-tenant IDs fail validation before reaching the business service.
            for field in ("customer", "warehouse"):
                self.fields[field].queryset = self.fields[field].queryset.filter(
                    organization=organization, is_active=True
                )

    def validate_lines(self, lines):
        organization = get_request_membership(self.context["request"]).organization
        for line in lines:
            product = (
                Product.objects.filter(
                    organization=organization, pk=line["product"], is_active=True
                )
                .select_related("unit")
                .first()
            )
            if product is None:
                raise serializers.ValidationError("Product is unavailable in this organization.")
            line["product"] = product
        return lines


class ShipmentLineInput(serializers.Serializer):
    order_line = serializers.UUIDField()
    quantity = serializers.DecimalField(
        max_digits=18, decimal_places=4, min_value=Decimal("0.0001")
    )


class ShipInput(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    lines = ShipmentLineInput(many=True, allow_empty=False)


class ReturnLineInput(serializers.Serializer):
    shipment_line = serializers.UUIDField()
    quantity = serializers.DecimalField(
        max_digits=18, decimal_places=4, min_value=Decimal("0.0001")
    )


@extend_schema_serializer(component_name="SalesReasonInput")
class ReasonInput(serializers.Serializer):
    reason = serializers.CharField(allow_blank=False, max_length=2000)


@extend_schema_serializer(component_name="SalesReturnInput")
class ReturnInput(ReasonInput):
    idempotency_key = serializers.UUIDField()
    lines = ReturnLineInput(many=True, allow_empty=False)


class EmptyInput(serializers.Serializer):
    # Confirmation needs no client-supplied totals or status values.
    pass


@extend_schema_serializer(component_name="SalesOrderLineOutput")
class OrderLineOutput(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = SalesOrderLine
        fields = ["id", "product", "product_name", "quantity", "unit_price", "shipped_quantity"]


class ShipmentLineOutput(serializers.ModelSerializer):
    product_name = serializers.CharField(source="order_line.product.name", read_only=True)

    class Meta:
        model = ShipmentLine
        fields = ["id", "order_line", "product_name", "quantity", "returned_quantity"]


class ReturnLineOutput(serializers.ModelSerializer):
    class Meta:
        model = CustomerReturnLine
        fields = ["id", "shipment_line", "quantity"]


class ReturnOutput(serializers.ModelSerializer):
    lines = ReturnLineOutput(many=True, read_only=True)

    class Meta:
        model = CustomerReturn
        fields = ["id", "shipment", "reason", "idempotency_key", "created_at", "lines"]


class ShipmentOutput(serializers.ModelSerializer):
    lines = ShipmentLineOutput(many=True, read_only=True)
    returns = ReturnOutput(many=True, read_only=True)

    class Meta:
        model = Shipment
        fields = ["id", "order", "idempotency_key", "created_at", "lines", "returns"]


@extend_schema_serializer(component_name="SalesOrderOutput")
class OrderOutput(serializers.ModelSerializer):
    lines = OrderLineOutput(many=True, read_only=True)
    shipments = ShipmentOutput(many=True, read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    history = serializers.SerializerMethodField()
    subtotal = serializers.SerializerMethodField()

    def get_subtotal(self, obj) -> str:
        # Week 5 displays a line subtotal only; tax/invoicing belongs to billing.
        return str(sum((line.quantity * line.unit_price for line in obj.lines.all()), Decimal(0)))

    def get_history(self, obj) -> list:
        return [dict(action=e.action, detail=e.detail, at=e.created_at) for e in obj.events.all()]

    class Meta:
        model = SalesOrder
        fields = [
            "id",
            "reference",
            "customer",
            "customer_name",
            "warehouse",
            "warehouse_name",
            "status",
            "notes",
            "lines",
            "shipments",
            "subtotal",
            "history",
            "created_at",
        ]
