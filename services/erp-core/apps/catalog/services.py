# Teaching edition: Perform business operations after checking the tenant and input.
from typing import Any

from django.db import transaction

from apps.catalog.models import Product


@transaction.atomic
def create_product(*, organization, actor, data: dict[str, Any]) -> Product:
    """Application-service extension point for future catalog business rules."""

    product = Product(organization=organization, created_by=actor, **data)
    product.full_clean()
    product.save()
    return product
