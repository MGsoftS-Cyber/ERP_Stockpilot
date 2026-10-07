from rest_framework import serializers
from rest_framework.routers import DefaultRouter

from apps.common.api import TenantReadViewSet

from .models import AuditEvent


class AuditOutput(serializers.ModelSerializer):
    class Meta:
        model = AuditEvent
        fields = ["id", "created_at", "created_by", "action", "entity_type", "entity_id", "detail"]


class AuditViewSet(TenantReadViewSet):
    queryset = AuditEvent.objects.all()
    serializer_class = AuditOutput


router = DefaultRouter()
router.register("events", AuditViewSet)
urlpatterns = router.urls
