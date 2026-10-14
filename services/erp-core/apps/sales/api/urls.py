from rest_framework.routers import DefaultRouter

from apps.sales.api.views import CustomerReturnViewSet, SalesOrderViewSet, ShipmentViewSet

# One module prefix /api/v1/sales/ keeps future API versions isolated.
router = DefaultRouter()
router.register("orders", SalesOrderViewSet, basename="sales-order")
router.register("shipments", ShipmentViewSet, basename="shipment")
router.register("returns", CustomerReturnViewSet, basename="customer-return")
urlpatterns = router.urls
