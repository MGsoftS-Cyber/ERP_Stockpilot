# Teaching edition: Build read queries within the selected organization.
from apps.partners.models import BusinessPartner


def partners_for_organization(organization):
    return BusinessPartner.objects.for_organization(organization)
