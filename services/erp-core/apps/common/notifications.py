"""Week 9: tenant-scoped change hint; this is not a durable event delivery API."""
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.models import AuditEvent
from apps.tenancy.services import get_request_membership


class NotificationSerializer(serializers.Serializer):
    revision = serializers.CharField(allow_null=True)


class NotificationRevisionView(APIView):
    @extend_schema(responses=NotificationSerializer)
    def get(self, request):
        membership = get_request_membership(request)
        # No financial details travel through WebSockets; clients refetch authorized APIs.
        latest = AuditEvent.objects.filter(organization=membership.organization).first()
        return Response({"revision": str(latest.id) if latest else None})
