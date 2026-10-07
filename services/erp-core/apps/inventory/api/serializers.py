# Teaching edition: Convert records to JSON and validate incoming API values.
from decimal import Decimal

from rest_framework import serializers

from apps.catalog.models import Product
from apps.inventory.models import (
    StockAdjustment,
    StockAdjustmentLine,
    StockBalance,
    StockMovement,
    StockReservation,
    StockTransfer,
    StockTransferLine,
    Warehouse,
)


class WarehouseSerializer(serializers.ModelSerializer):
    # Django metadata: schema or API options, not a constructor.
    class Meta:
        model = Warehouse
        fields = ["id", "code", "name", "address", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class StockMovementSerializer(serializers.ModelSerializer):
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    warehouse_code = serializers.CharField(source="warehouse.code", read_only=True)
    movement_type_label = serializers.CharField(source="get_movement_type_display", read_only=True)
    created_by_email = serializers.EmailField(
        source="created_by.email",
        read_only=True,
        allow_null=True,
    )

    # Django metadata: schema or API options, not a constructor.
    class Meta:
        model = StockMovement
        fields = [
            "id",
            "product",
            "product_sku",
            "product_name",
            "warehouse",
            "warehouse_code",
            "movement_type",
            "movement_type_label",
            "quantity_signed",
            "unit_cost",
            "occurred_at",
            "source_type",
            "source_id",
            "idempotency_key",
            "created_by_email",
            "created_at",
        ]


class StockBalanceSerializer(serializers.ModelSerializer):
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    warehouse_code = serializers.CharField(source="warehouse.code", read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    available = serializers.DecimalField(max_digits=18, decimal_places=4, read_only=True)
    is_low_stock = serializers.BooleanField(read_only=True)

    # Django metadata: schema or API options, not a constructor.
    class Meta:
        model = StockBalance
        fields = [
            "id",
            "product",
            "product_sku",
            "product_name",
            "warehouse",
            "warehouse_code",
            "warehouse_name",
            "on_hand",
            "reserved",
            "available",
            "is_low_stock",
            "updated_at",
        ]


class AdjustmentLineInputSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    quantity_signed = serializers.DecimalField(max_digits=18, decimal_places=4)
    unit_cost = serializers.DecimalField(
        max_digits=18,
        decimal_places=4,
        min_value=Decimal("0"),
        default=Decimal("0"),
    )


class StockAdjustmentWriteSerializer(serializers.Serializer):
    reference = serializers.CharField(max_length=64, required=False, allow_blank=True)
    warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.all())
    reason = serializers.CharField()
    idempotency_key = serializers.UUIDField()
    lines = AdjustmentLineInputSerializer(many=True, allow_empty=False)

    # Reject invalid input combinations before saving or calling services.
    def validate(self, attrs):
        organization = self.context["request"].organization
        if attrs["warehouse"].organization_id != organization.id:
            raise serializers.ValidationError(
                {"warehouse": "Must belong to the selected organization."}
            )
        product_ids = []
        for line in attrs["lines"]:
            if line["product"].organization_id != organization.id:
                raise serializers.ValidationError(
                    {"lines": "Every product must belong to the selected organization."}
                )
            if line["quantity_signed"] == 0:
                raise serializers.ValidationError(
                    {"lines": "Adjustment quantities must not be zero."}
                )
            product_ids.append(line["product"].id)
        if len(product_ids) != len(set(product_ids)):
            raise serializers.ValidationError({"lines": "A product can appear only once."})
        return attrs


class StockAdjustmentLineSerializer(serializers.ModelSerializer):
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)

    # Django metadata: schema or API options, not a constructor.
    class Meta:
        model = StockAdjustmentLine
        fields = [
            "id",
            "product",
            "product_sku",
            "product_name",
            "quantity_signed",
            "unit_cost",
        ]


class StockAdjustmentSerializer(serializers.ModelSerializer):
    warehouse_code = serializers.CharField(source="warehouse.code", read_only=True)
    lines = StockAdjustmentLineSerializer(many=True, read_only=True)

    # Django metadata: schema or API options, not a constructor.
    class Meta:
        model = StockAdjustment
        fields = [
            "id",
            "reference",
            "warehouse",
            "warehouse_code",
            "reason",
            "idempotency_key",
            "posted_at",
            "lines",
        ]


class TransferLineInputSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    quantity = serializers.DecimalField(
        max_digits=18,
        decimal_places=4,
        min_value=Decimal("0.0001"),
    )
    unit_cost = serializers.DecimalField(
        max_digits=18,
        decimal_places=4,
        min_value=Decimal("0"),
        default=Decimal("0"),
    )


class StockTransferWriteSerializer(serializers.Serializer):
    reference = serializers.CharField(max_length=64, required=False, allow_blank=True)
    source_warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.all())
    destination_warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.all())
    reason = serializers.CharField(required=False, allow_blank=True)
    idempotency_key = serializers.UUIDField()
    lines = TransferLineInputSerializer(many=True, allow_empty=False)

    # Reject invalid input combinations before saving or calling services.
    def validate(self, attrs):
        organization = self.context["request"].organization
        source = attrs["source_warehouse"]
        destination = attrs["destination_warehouse"]
        if source.organization_id != organization.id:
            raise serializers.ValidationError(
                {"source_warehouse": "Must belong to the selected organization."}
            )
        if destination.organization_id != organization.id:
            raise serializers.ValidationError(
                {"destination_warehouse": "Must belong to the selected organization."}
            )
        if source.id == destination.id:
            raise serializers.ValidationError(
                {"destination_warehouse": "Must differ from source warehouse."}
            )
        product_ids = []
        for line in attrs["lines"]:
            if line["product"].organization_id != organization.id:
                raise serializers.ValidationError(
                    {"lines": "Every product must belong to the selected organization."}
                )
            product_ids.append(line["product"].id)
        if len(product_ids) != len(set(product_ids)):
            raise serializers.ValidationError({"lines": "A product can appear only once."})
        return attrs


class StockTransferLineSerializer(serializers.ModelSerializer):
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)

    # Django metadata: schema or API options, not a constructor.
    class Meta:
        model = StockTransferLine
        fields = ["id", "product", "product_sku", "product_name", "quantity", "unit_cost"]


class StockTransferSerializer(serializers.ModelSerializer):
    source_warehouse_code = serializers.CharField(
        source="source_warehouse.code",
        read_only=True,
    )
    destination_warehouse_code = serializers.CharField(
        source="destination_warehouse.code",
        read_only=True,
    )
    lines = StockTransferLineSerializer(many=True, read_only=True)

    # Django metadata: schema or API options, not a constructor.
    class Meta:
        model = StockTransfer
        fields = [
            "id",
            "reference",
            "source_warehouse",
            "source_warehouse_code",
            "destination_warehouse",
            "destination_warehouse_code",
            "reason",
            "idempotency_key",
            "transferred_at",
            "lines",
        ]


class StockReservationWriteSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.all())
    quantity = serializers.DecimalField(
        max_digits=18,
        decimal_places=4,
        min_value=Decimal("0.0001"),
    )
    source_type = serializers.ChoiceField(choices=StockReservation.SourceType.choices)
    source_id = serializers.UUIDField()
    idempotency_key = serializers.UUIDField()

    def validate_source_type(self, value):
        # Only the sales confirmation service can create an order-owned reservation.
        if value == StockReservation.SourceType.SALES_ORDER:
            raise serializers.ValidationError("Confirm a sales order to reserve its stock.")
        return value

    # Reject invalid input combinations before saving or calling services.
    def validate(self, attrs):
        organization = self.context["request"].organization
        for field in ("product", "warehouse"):
            if attrs[field].organization_id != organization.id:
                raise serializers.ValidationError(
                    {field: "Must belong to the selected organization."}
                )
        return attrs


class StockReservationSerializer(serializers.ModelSerializer):
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    warehouse_code = serializers.CharField(source="warehouse.code", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    # Django metadata: schema or API options, not a constructor.
    class Meta:
        model = StockReservation
        fields = [
            "id",
            "product",
            "product_sku",
            "warehouse",
            "warehouse_code",
            "quantity",
            "source_type",
            "source_id",
            "status",
            "status_label",
            "idempotency_key",
            "created_at",
            "released_at",
            "fulfilled_quantity",
        ]


class ReconciliationItemSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    warehouse_id = serializers.UUIDField()
    ledger_total = serializers.DecimalField(max_digits=18, decimal_places=4)
    balance_on_hand = serializers.DecimalField(max_digits=18, decimal_places=4)
    is_reconciled = serializers.BooleanField()


class ReconciliationReportSerializer(serializers.Serializer):
    is_reconciled = serializers.BooleanField()
    items = ReconciliationItemSerializer(many=True)
