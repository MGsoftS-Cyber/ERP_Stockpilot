# Teaching edition: Group business module routes under the versioned API.
from django.urls import include, path

from apps.common.notifications import NotificationRevisionView
from apps.common.views import HealthView

urlpatterns = [
    path("plugins/", include("apps.extensions.api")),
    path("notifications/revision/", NotificationRevisionView.as_view()),
    path("health/", HealthView.as_view(), name="health"),
    path("auth/", include("apps.tenancy.api.auth_urls")),
    path("organizations/", include("apps.tenancy.api.organization_urls")),
    path("catalog/", include("apps.catalog.api.urls")),
    path("partners/", include("apps.partners.api.urls")),
    path("inventory/", include("apps.inventory.api.urls")),
    path("purchasing/", include("apps.purchasing.api.urls")),
    path("sales/", include("apps.sales.api.urls")),
    path("billing/", include("apps.billing.api")),
    path("finance/", include("apps.finance.api")),
    path("audit/", include("apps.audit.api")),
    path("intelligence/", include("apps.intelligence.api")),
]
