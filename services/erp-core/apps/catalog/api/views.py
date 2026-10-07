# Teaching edition: Handle HTTP requests and delegate validation and business work.
from apps.catalog.api.serializers import (
    CategorySerializer,
    ProductSerializer,
    TaxRateSerializer,
    UnitOfMeasureSerializer,
)
from apps.catalog.models import Category, Product, TaxRate, UnitOfMeasure
from apps.common.viewsets import OrganizationScopedModelViewSet


class CategoryViewSet(OrganizationScopedModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer


class UnitOfMeasureViewSet(OrganizationScopedModelViewSet):
    queryset = UnitOfMeasure.objects.all()
    serializer_class = UnitOfMeasureSerializer


class TaxRateViewSet(OrganizationScopedModelViewSet):
    queryset = TaxRate.objects.all()
    serializer_class = TaxRateSerializer


class ProductViewSet(OrganizationScopedModelViewSet):
    queryset = Product.objects.select_related("category", "unit", "tax_rate")
    serializer_class = ProductSerializer
