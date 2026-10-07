# Teaching edition: Handle HTTP requests and delegate validation and business work.
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        responses=inline_serializer(
            "HealthResponse",
            fields={
                "status": serializers.CharField(),
                "service": serializers.CharField(),
            },
        )
    )
    def get(self, request) -> Response:
        return Response({"status": "ok", "service": "stockpilot-erp-core"})
