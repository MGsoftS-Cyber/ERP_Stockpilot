# Teaching edition: Map URLs to views; routers generate list and detail routes.
from rest_framework.routers import DefaultRouter

from apps.partners.api.views import BusinessPartnerViewSet

router = DefaultRouter()
router.register("business-partners", BusinessPartnerViewSet, basename="business-partner")

urlpatterns = router.urls
