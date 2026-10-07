# Teaching edition: Perform business operations after checking the tenant and input.
from typing import Any

from django.db import transaction

from apps.partners.models import BusinessPartner


@transaction.atomic
def create_business_partner(*, organization, actor, data: dict[str, Any]) -> BusinessPartner:
    partner = BusinessPartner(organization=organization, created_by=actor, **data)
    partner.full_clean()
    partner.save()
    return partner
