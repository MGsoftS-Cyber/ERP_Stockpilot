# Teaching edition: Handle HTTP requests and delegate validation and business work.
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.permissions import TenantRolePermission
from apps.purchasing.api.serializers import (
    OrderInput,
    OrderOutput,
    ReceiptInput,
    ReceiptOutput,
    TransitionInput,
)
from apps.purchasing.models import GoodsReceipt, PurchaseOrder
from apps.purchasing.services import (
    RECEIVERS,
    create_order,
    receive_goods,
    revise_order,
    transition_order,
)
from apps.tenancy.services import get_request_membership


class ScopedReadViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated, TenantRolePermission]
    write_roles = RECEIVERS  # Services enforce narrower, action-specific roles.

    # Filter the base query before list/detail objects can be retrieved.
    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset.none()
        return self.queryset.filter(organization=get_request_membership(self.request).organization)


class PurchaseOrderViewSet(mixins.CreateModelMixin, ScopedReadViewSet):
    queryset = PurchaseOrder.objects.select_related("supplier").prefetch_related(
        "lines__product", "events"
    )
    serializer_class = OrderOutput

    # Validate creation input, run the operation and serialize the result.
    @extend_schema(request=OrderInput, responses={201: OrderOutput})
    def create(self, request):
        data = OrderInput(data=request.data, context={"request": request})
        data.is_valid(raise_exception=True)
        order = create_order(
            organization=get_request_membership(request).organization,
            actor=request.user,
            **data.validated_data,
        )
        return Response(OrderOutput(order).data, status=201)

    # Pass an action name for the service to validate role and state.
    @extend_schema(request=TransitionInput, responses=OrderOutput)
    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        self.get_object()
        data = TransitionInput(data=request.data)
        data.is_valid(raise_exception=True)
        order = transition_order(
            organization=get_request_membership(request).organization,
            actor=request.user,
            order_id=pk,
            **data.validated_data,
        )
        return Response(OrderOutput(order).data)

    # Submit a replacement draft; posted documents cannot be edited.
    @extend_schema(request=OrderInput, responses=OrderOutput)
    @action(detail=True, methods=["post"])
    def revise(self, request, pk=None):
        self.get_object()
        data = OrderInput(data=request.data, context={"request": request})
        data.is_valid(raise_exception=True)
        order = revise_order(
            organization=get_request_membership(request).organization,
            actor=request.user,
            order_id=pk,
            **data.validated_data,
        )
        return Response(OrderOutput(order).data)

    # Call the atomic receipt service instead of editing stock directly.
    @extend_schema(request=ReceiptInput, responses={200: ReceiptOutput, 201: ReceiptOutput})
    @action(detail=True, methods=["post"])
    def receive(self, request, pk=None):
        self.get_object()
        data = ReceiptInput(data=request.data, context={"request": request})
        data.is_valid(raise_exception=True)
        receipt, created = receive_goods(
            organization=get_request_membership(request).organization,
            actor=request.user,
            order_id=pk,
            **data.validated_data,
        )
        return Response(ReceiptOutput(receipt).data, status=201 if created else 200)


class GoodsReceiptViewSet(ScopedReadViewSet):
    queryset = GoodsReceipt.objects.prefetch_related("lines")
    serializer_class = ReceiptOutput
