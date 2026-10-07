# Teaching edition: Map URLs to views; routers generate list and detail routes.
from rest_framework.routers import DefaultRouter

from apps.catalog.api.views import (
    CategoryViewSet,
    ProductViewSet,
    TaxRateViewSet,
    UnitOfMeasureViewSet,
)

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("units", UnitOfMeasureViewSet, basename="unit")
router.register("tax-rates", TaxRateViewSet, basename="tax-rate")
router.register("products", ProductViewSet, basename="product")

urlpatterns = router.urls
