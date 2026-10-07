# Teaching edition: Expose organizations available to the authenticated user.
from rest_framework.routers import DefaultRouter

from apps.tenancy.api.views import OrganizationViewSet

router = DefaultRouter()
router.register("", OrganizationViewSet, basename="organization")

urlpatterns = router.urls
