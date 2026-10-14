"""HTTP orchestration only: all mutations delegate to sales services."""

from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.permissions import TenantRolePermission
from apps.sales import services
from apps.sales.api.serializers import (
    DraftInput,
    EmptyInput,
    OrderOutput,
    ReasonInput,
    ReturnInput,
    ReturnOutput,
    ShipInput,
    ShipmentOutput,
)
from apps.sales.models import CustomerReturn, SalesOrder, Shipment
from apps.tenancy.services import get_request_membership


class TenantReadViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated, TenantRolePermission]
    write_roles = (*services.SELLERS, "STOCK_OPERATOR")

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset.none()
        return self.queryset.filter(organization=get_request_membership(self.request).organization)

    def command_args(self):
        return dict(
            organization=get_request_membership(self.request).organization,
            actor=self.request.user,
        )

    def validated(self, serializer):
        value = serializer(data=self.request.data, context={"request": self.request})
        value.is_valid(raise_exception=True)
        return value.validated_data


class SalesOrderViewSet(mixins.CreateModelMixin, TenantReadViewSet):
    queryset = SalesOrder.objects.select_related("customer", "warehouse").prefetch_related(
        "lines__product",
        "events",
        "shipments__lines__order_line__product",
        "shipments__returns__lines",
    )
    serializer_class = OrderOutput

    @extend_schema(request=DraftInput, responses={201: OrderOutput})
    def create(self, request):
        order = services.save_draft(**self.command_args(), **self.validated(DraftInput))
        return Response(OrderOutput(order).data, status=201)

    @extend_schema(request=DraftInput, responses=OrderOutput)
    @action(detail=True, methods=["post"])
    def revise(self, request, pk=None):
        self.get_object()  # Never pass an unscoped object identifier to the service.
        order = services.save_draft(
            **self.command_args(), order_id=pk, **self.validated(DraftInput)
        )
        return Response(OrderOutput(order).data)

    @extend_schema(request=EmptyInput, responses=OrderOutput)
    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        self.get_object()
        order = services.confirm_order(**self.command_args(), order_id=pk)
        return Response(OrderOutput(order).data)

    @extend_schema(request=ReasonInput, responses=OrderOutput)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        self.get_object()
        order = services.cancel_order(
            **self.command_args(), order_id=pk, **self.validated(ReasonInput)
        )
        return Response(OrderOutput(order).data)

    @extend_schema(request=ShipInput, responses={200: ShipmentOutput, 201: ShipmentOutput})
    @action(detail=True, methods=["post"])
    def ship(self, request, pk=None):
        self.get_object()
        shipment, created = services.ship_order(
            **self.command_args(), order_id=pk, **self.validated(ShipInput)
        )
        return Response(ShipmentOutput(shipment).data, status=201 if created else 200)


class ShipmentViewSet(TenantReadViewSet):
    queryset = Shipment.objects.prefetch_related("lines__order_line__product", "returns__lines")
    serializer_class = ShipmentOutput

    @extend_schema(request=ReturnInput, responses={200: ReturnOutput, 201: ReturnOutput})
    @action(detail=True, methods=["post"], url_path="return")
    def return_goods(self, request, pk=None):
        self.get_object()
        returned, created = services.return_goods(
            **self.command_args(), shipment_id=pk, **self.validated(ReturnInput)
        )
        return Response(ReturnOutput(returned).data, status=201 if created else 200)


class CustomerReturnViewSet(TenantReadViewSet):
    queryset = CustomerReturn.objects.prefetch_related("lines")
    serializer_class = ReturnOutput
