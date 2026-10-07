# Teaching edition: Configure Django admin separately from the React interface.
from django.contrib import admin

from apps.partners.models import BusinessPartner

admin.site.register(BusinessPartner)
