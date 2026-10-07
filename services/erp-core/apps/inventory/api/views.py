# Teaching edition: Handle HTTP requests and delegate validation and business work.
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import TenantRolePermission
from apps.common.viewsets import OrganizationScopedModelViewSet
from apps.inventory.api.serializers import (
    ReconciliationItemSerializer,
    ReconciliationReportSerializer,
    StockAdjustmentSerializer,
    StockAdjustmentWriteSerializer,
    StockBalanceSerializer,
    StockMovementSerializer,
    StockReservationSerializer,
    StockReservationWriteSerializer,
    StockTransferSerializer,
    StockTransferWriteSerializer,
    WarehouseSerializer,
)
from apps.inventory.models import (
    StockAdjustment,
    StockBalance,
    StockMovement,
    StockReservation,
    StockTransfer,
    Warehouse,
)
from apps.inventory.services import (
    post_stock_adjustment,
    reconciliation_report,
    release_reservation,
    reserve_stock,
    transfer_stock,
)
from apps.tenancy.models import Membership
from apps.tenancy.services import get_request_membership


class WarehouseViewSet(OrganizationScopedModelViewSet):
    queryset = Warehouse.objects.all()
    serializer_class = WarehouseSerializer
    write_roles = (
        Membership.Role.ADMINISTRATOR,
        Membership.Role.MANAGER,
        Membership.Role.STOCK_OPERATOR,
    )


class OrganizationScopedReadOnlyViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated, TenantRolePermission]

    # Filter the base query before list/detail objects can be retrieved.
    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return super().get_queryset().none()
        membership = get_request_membership(self.request)
        return super().get_queryset().for_organization(membership.organization)


class StockMovementViewSet(OrganizationScopedReadOnlyViewSet):
    queryset = StockMovement.objects.select_related("product", "warehouse", "created_by")
    serializer_class = StockMovementSerializer

    # Filter the base query before list/detail objects can be retrieved.
    def get_queryset(self):
        queryset = super().get_queryset()
        product_id = self.request.query_params.get("product")
        warehouse_id = self.request.query_params.get("warehouse")
        if product_id:
            queryset = queryset.filter(product_id=product_id)
        if warehouse_id:
            queryset = queryset.filter(warehouse_id=warehouse_id)
        return queryset


class StockBalanceViewSet(OrganizationScopedReadOnlyViewSet):
    queryset = StockBalance.objects.select_related("product", "warehouse")
    serializer_class = StockBalanceSerializer


class StockAdjustmentViewSet(OrganizationScopedReadOnlyViewSet):
    queryset = StockAdjustment.objects.select_related("warehouse").prefetch_related(
        "lines__product"
    )
    serializer_class = StockAdjustmentSerializer
    write_roles = (
        Membership.Role.ADMINISTRATOR,
        Membership.Role.MANAGER,
        Membership.Role.STOCK_OPERATOR,
    )

    # Select the write contract or the read representation.
    def get_serializer_class(self):
        if self.action == "create":
            return StockAdjustmentWriteSerializer
        return StockAdjustmentSerializer

    # Validate creation input, run the operation and serialize the result.
    @extend_schema(
        request=StockAdjustmentWriteSerializer,
        responses={
            200: StockAdjustmentSerializer,
            201: StockAdjustmentSerializer,
            409: OpenApiResponse(description="Insufficient available stock."),
        },
    )
    def create(self, request) -> Response:
        membership = get_request_membership(request)
        serializer = StockAdjustmentWriteSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        adjustment, created = post_stock_adjustment(
            organization=membership.organization,
            actor=request.user,
            **serializer.validated_data,
        )
        output = StockAdjustmentSerializer(adjustment)
        return Response(
            output.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class StockTransferViewSet(OrganizationScopedReadOnlyViewSet):
    queryset = StockTransfer.objects.select_related(
        "source_warehouse",
        "destination_warehouse",
    ).prefetch_related("lines__product")
    serializer_class = StockTransferSerializer
    write_roles = (
        Membership.Role.ADMINISTRATOR,
        Membership.Role.MANAGER,
        Membership.Role.STOCK_OPERATOR,
    )

    # Select the write contract or the read representation.
    def get_serializer_class(self):
        if self.action == "create":
            return StockTransferWriteSerializer
        return StockTransferSerializer

    # Validate creation input, run the operation and serialize the result.
    @extend_schema(
        request=StockTransferWriteSerializer,
        responses={
            200: StockTransferSerializer,
            201: StockTransferSerializer,
            409: OpenApiResponse(description="Insufficient source stock."),
        },
    )
    def create(self, request) -> Response:
        membership = get_request_membership(request)
        serializer = StockTransferWriteSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        transfer, created = transfer_stock(
            organization=membership.organization,
            actor=request.user,
            **serializer.validated_data,
        )
        output = StockTransferSerializer(transfer)
        return Response(
            output.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class StockReservationViewSet(OrganizationScopedReadOnlyViewSet):
    queryset = StockReservation.objects.select_related("product", "warehouse")
    serializer_class = StockReservationSerializer
    write_roles = (
        Membership.Role.ADMINISTRATOR,
        Membership.Role.MANAGER,
        Membership.Role.STOCK_OPERATOR,
        Membership.Role.SALES_AGENT,
    )

    # Select the write contract or the read representation.
    def get_serializer_class(self):
        if self.action == "create":
            return StockReservationWriteSerializer
        return StockReservationSerializer

    # Validate creation input, run the operation and serialize the result.
    @extend_schema(
        request=StockReservationWriteSerializer,
        responses={
            200: StockReservationSerializer,
            201: StockReservationSerializer,
            409: OpenApiResponse(description="Insufficient available stock."),
        },
    )
    def create(self, request) -> Response:
        membership = get_request_membership(request)
        serializer = StockReservationWriteSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        reservation, created = reserve_stock(
            organization=membership.organization,
            actor=request.user,
            **serializer.validated_data,
        )
        return Response(
            StockReservationSerializer(reservation).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    # Release an eligible reservation once; sales uses order cancellation.
    @extend_schema(request=None, responses=StockReservationSerializer)
    @action(detail=True, methods=["post"])
    def release(self, request, pk=None) -> Response:
        membership = get_request_membership(request)
        reservation = release_reservation(
            organization=membership.organization,
            reservation_id=pk,
        )
        return Response(StockReservationSerializer(reservation).data)


class ReconciliationView(APIView):
    permission_classes = [IsAuthenticated, TenantRolePermission]

    @extend_schema(responses=ReconciliationReportSerializer)
    def get(self, request) -> Response:
        membership = get_request_membership(request)
        items = reconciliation_report(organization=membership.organization)
        serializer = ReconciliationItemSerializer(items, many=True)
        return Response(
            {
                "is_reconciled": all(item.is_reconciled for item in items),
                "items": serializer.data,
            }
        )
