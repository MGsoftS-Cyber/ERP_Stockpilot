# Teaching edition: Map URLs to views; routers generate list and detail routes.
from rest_framework.routers import DefaultRouter

from apps.purchasing.api.views import GoodsReceiptViewSet, PurchaseOrderViewSet

router = DefaultRouter()
router.register("orders", PurchaseOrderViewSet, basename="purchase-order")
router.register("receipts", GoodsReceiptViewSet, basename="goods-receipt")
urlpatterns = router.urls
