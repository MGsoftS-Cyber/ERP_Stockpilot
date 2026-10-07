# Teaching edition: Handle HTTP requests and delegate validation and business work.
from apps.common.viewsets import OrganizationScopedModelViewSet
from apps.partners.api.serializers import BusinessPartnerSerializer
from apps.partners.models import BusinessPartner


class BusinessPartnerViewSet(OrganizationScopedModelViewSet):
    queryset = BusinessPartner.objects.all()
    serializer_class = BusinessPartnerSerializer
