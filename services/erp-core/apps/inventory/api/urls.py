# Teaching edition: Map URLs to views; routers generate list and detail routes.
from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.inventory.api.views import (
    ReconciliationView,
    StockAdjustmentViewSet,
    StockBalanceViewSet,
    StockMovementViewSet,
    StockReservationViewSet,
    StockTransferViewSet,
    WarehouseViewSet,
)

router = DefaultRouter()
router.register("warehouses", WarehouseViewSet, basename="warehouse")
router.register("stock-movements", StockMovementViewSet, basename="stock-movement")
router.register("stock-balances", StockBalanceViewSet, basename="stock-balance")
router.register("stock-adjustments", StockAdjustmentViewSet, basename="stock-adjustment")
router.register("stock-transfers", StockTransferViewSet, basename="stock-transfer")
router.register("stock-reservations", StockReservationViewSet, basename="stock-reservation")

urlpatterns = [
    path("reconciliation/", ReconciliationView.as_view(), name="inventory-reconciliation"),
    *router.urls,
]
