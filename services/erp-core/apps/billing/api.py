from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter

from apps.common.api import CurrencyInput, EmptyInput, ReasonInput, TenantReadViewSet

from . import services
from .models import Invoice, InvoiceLine, Payment, PaymentAllocation


class LineInput(serializers.Serializer):
    product_id = serializers.UUIDField(required=False, allow_null=True)
    description = serializers.CharField(max_length=240)
    quantity = serializers.DecimalField(max_digits=18, decimal_places=4, min_value=0)
    unit_price = serializers.DecimalField(max_digits=18, decimal_places=4, min_value=0)
    unit_cost = serializers.DecimalField(
        max_digits=18, decimal_places=4, min_value=0, required=False
    )
    tax_rate = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=0, max_value=100, default=0
    )


class DraftInput(CurrencyInput):
    idempotency_key = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=Invoice.Kind.choices)
    partner_id = serializers.UUIDField()
    reference = serializers.CharField(max_length=64)
    issued_on = serializers.DateField()
    due_on = serializers.DateField()
    lines = LineInput(many=True, allow_empty=True, max_length=100)
    sales_order_id = serializers.UUIDField(required=False, allow_null=True)
    purchase_order_id = serializers.UUIDField(required=False, allow_null=True)


class AllocationInput(serializers.Serializer):
    invoice_id = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)


class PaymentInput(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    paid_on = serializers.DateField()
    reference = serializers.CharField(max_length=120)
    allocations = AllocationInput(many=True, allow_empty=False, max_length=100)


class LineOutput(serializers.ModelSerializer):
    class Meta:
        model = InvoiceLine
        fields = [
            "id",
            "product",
            "description",
            "quantity",
            "unit_price",
            "unit_cost",
            "tax_rate",
            "net",
            "tax",
        ]


class InvoiceOutput(serializers.ModelSerializer):
    lines = LineOutput(many=True, read_only=True)
    partner_name = serializers.CharField(source="partner.name", read_only=True)
    balance = serializers.SerializerMethodField()

    def get_balance(self, obj) -> str:
        return str(obj.total - obj.paid)

    class Meta:
        model = Invoice
        fields = [
            "id",
            "kind",
            "partner",
            "partner_name",
            "reference",
            "currency",
            "issued_on",
            "due_on",
            "status",
            "subtotal",
            "tax_total",
            "total",
            "paid",
            "balance",
            "cost_total",
            "lines",
            "sales_order",
            "purchase_order",
            "created_at",
        ]


class AllocationOutput(serializers.ModelSerializer):
    class Meta:
        model = PaymentAllocation
        fields = ["invoice", "amount"]


class PaymentOutput(serializers.ModelSerializer):
    allocations = AllocationOutput(many=True, read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id",
            "partner",
            "kind",
            "currency",
            "amount",
            "paid_on",
            "reference",
            "allocations",
        ]


class InvoiceViewSet(mixins.CreateModelMixin, TenantReadViewSet):
    queryset = Invoice.objects.select_related("partner").prefetch_related("lines")
    serializer_class = InvoiceOutput

    @extend_schema(request=DraftInput, responses=InvoiceOutput)
    def create(self, request):
        obj, created = services.create_invoice(**self.command_args(), **self.validate(DraftInput))
        return Response(InvoiceOutput(obj).data, status=201 if created else 200)

    @extend_schema(request=EmptyInput, responses=InvoiceOutput)
    @action(detail=True, methods=["post"])
    def post(self, request, pk=None):
        self.get_object()
        obj = services.change_status(**self.command_args(), invoice_id=pk, target="POSTED")
        return Response(InvoiceOutput(obj).data)

    @extend_schema(request=ReasonInput, responses=InvoiceOutput)
    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        self.get_object()
        obj = services.change_status(
            **self.command_args(), invoice_id=pk, target="VOID", **self.validate(ReasonInput)
        )
        return Response(InvoiceOutput(obj).data)


class PaymentViewSet(mixins.CreateModelMixin, TenantReadViewSet):
    queryset = Payment.objects.prefetch_related("allocations")
    serializer_class = PaymentOutput

    @extend_schema(request=PaymentInput, responses=PaymentOutput)
    def create(self, request):
        obj, created = services.allocate_payment(
            **self.command_args(), **self.validate(PaymentInput)
        )
        return Response(PaymentOutput(obj).data, status=201 if created else 200)


router = DefaultRouter()
router.register("invoices", InvoiceViewSet)
router.register("payments", PaymentViewSet)
urlpatterns = router.urls
