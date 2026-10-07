# Teaching edition: Convert records to JSON and validate incoming API values.
from decimal import Decimal

from rest_framework import serializers

from apps.catalog.models import Product
from apps.inventory.models import Warehouse
from apps.partners.models import BusinessPartner
from apps.purchasing.models import GoodsReceipt, GoodsReceiptLine, PurchaseOrder, PurchaseOrderLine
from apps.tenancy.services import get_request_membership


class TenantInput(serializers.Serializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and not getattr(request, "swagger_fake_view", False):
            organization = get_request_membership(request).organization
            for field in self.fields.values():
                if isinstance(field, serializers.PrimaryKeyRelatedField):
                    field.queryset = field.queryset.filter(
                        organization=organization, is_active=True
                    )


class OrderLineInput(serializers.Serializer):
    product = serializers.UUIDField()
    quantity = serializers.DecimalField(
        max_digits=18, decimal_places=4, min_value=Decimal("0.0001")
    )
    unit_price = serializers.DecimalField(max_digits=18, decimal_places=4, min_value=Decimal("0"))


class OrderInput(TenantInput):
    supplier = serializers.PrimaryKeyRelatedField(queryset=BusinessPartner.objects.all())
    notes = serializers.CharField(required=False, allow_blank=True)
    lines = OrderLineInput(many=True, allow_empty=False)

    # Resolve product identifiers within the authenticated organization.
    def validate_lines(self, lines):
        organization = get_request_membership(self.context["request"]).organization
        for line in lines:
            product = Product.objects.filter(
                organization=organization, pk=line["product"], is_active=True
            ).first()
            if product is None:
                raise serializers.ValidationError("Product is unavailable in this organization.")
            line["product"] = product
        return lines


class ReceiptLineInput(serializers.Serializer):
    order_line = serializers.UUIDField()
    quantity = serializers.DecimalField(
        max_digits=18, decimal_places=4, min_value=Decimal("0.0001")
    )


class ReceiptInput(TenantInput):
    warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.all())
    idempotency_key = serializers.UUIDField()
    lines = ReceiptLineInput(many=True, allow_empty=False)


class TransitionInput(serializers.Serializer):
    action = serializers.ChoiceField(
        choices=[
            "submit",
            "approve",
            "return_to_draft",
            "cancel",
            "close",
        ]
    )
    reason = serializers.CharField(required=False, allow_blank=True)


class OrderLineOutput(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)

    # Django metadata: schema or API options, not a constructor.
    class Meta:
        model = PurchaseOrderLine
        fields = ["id", "product", "product_name", "quantity", "received_quantity", "unit_price"]


class OrderOutput(serializers.ModelSerializer):
    lines = OrderLineOutput(many=True, read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    subtotal = serializers.SerializerMethodField()
    history = serializers.SerializerMethodField()

    # Sum exact decimal line values; this is not an invoice tax calculation.
    def get_subtotal(self, obj) -> str:
        return str(sum((line.quantity * line.unit_price for line in obj.lines.all()), Decimal(0)))

    # Expose ordered business events for the document detail page.
    def get_history(self, obj) -> list:
        return [
            {
                "action": e.action,
                "detail": e.detail,
                "at": e.created_at,
                "actor": str(e.created_by_id),
            }
            for e in obj.events.all()
        ]

    # Django metadata: schema or API options, not a constructor.
    class Meta:
        model = PurchaseOrder
        fields = [
            "id",
            "reference",
            "supplier",
            "supplier_name",
            "status",
            "notes",
            "subtotal",
            "lines",
            "history",
            "created_at",
        ]


class ReceiptLineOutput(serializers.ModelSerializer):
    # Django metadata: schema or API options, not a constructor.
    class Meta:
        model = GoodsReceiptLine
        fields = ["id", "order_line", "quantity"]


class ReceiptOutput(serializers.ModelSerializer):
    lines = ReceiptLineOutput(many=True, read_only=True)

    # Django metadata: schema or API options, not a constructor.
    class Meta:
        model = GoodsReceipt
        fields = ["id", "order", "warehouse", "idempotency_key", "created_at", "lines"]
