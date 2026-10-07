# Appearance API: validates a small set of design tokens for one organization.
# Administrators save with an expected revision; all active members may read their company’s
# settings.
# React DesignProvider consumes these values; no arbitrary CSS or scripts are executed.
"""Validated design tokens; changing settings is optional and tenant-scoped."""

from django.db import transaction
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record
from apps.common.commands import Conflict
from apps.extensions.marketplace import administrator
from apps.extensions.models import Appearance
from apps.tenancy.models import Organization
from apps.tenancy.services import get_request_membership

DEFAULTS = {
    "primary": "#1f5d50",
    "secondary": "#d58b34",
    "background": "#f7f9f8",
    "radius": 10,
    "font_size": 14,
    "mode": "light",
    "density": "standard",
}


class TokensSerializer(serializers.Serializer):
    primary = serializers.RegexField(r"^#[0-9a-fA-F]{6}$")
    secondary = serializers.RegexField(r"^#[0-9a-fA-F]{6}$")
    background = serializers.RegexField(r"^#[0-9a-fA-F]{6}$")
    radius = serializers.IntegerField(min_value=0, max_value=24)
    font_size = serializers.IntegerField(min_value=12, max_value=20)
    mode = serializers.ChoiceField(choices=["light", "dark"])
    density = serializers.ChoiceField(choices=["standard", "compact"])


class SaveSerializer(serializers.Serializer):
    settings = TokensSerializer()
    expected_revision = serializers.IntegerField(min_value=0)


class AppearanceView(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        member = get_request_membership(request)
        row = Appearance.objects.filter(organization=member.organization).first()
        return Response(
            {
                "settings": row.settings if row else DEFAULTS,
                "revision": row.revision if row else 0,
                "customized": bool(row),
            }
        )

    @extend_schema(request=SaveSerializer, responses=OpenApiTypes.OBJECT)
    @transaction.atomic
    def put(self, request):
        member = administrator(request)
        data = SaveSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        Organization.objects.select_for_update().get(pk=member.organization_id)
        row = Appearance.objects.filter(organization=member.organization).first()
        if data.validated_data["expected_revision"] != (row.revision if row else 0):
            raise Conflict("Design changed. Reload before saving again.")
        if row is None:
            row = Appearance(organization=member.organization, created_by=request.user)
        else:
            row.revision += 1
        row.settings = data.validated_data["settings"]
        row.save()
        record(member.organization, request.user, "design.save", row, revision=row.revision)
        return Response({"settings": row.settings, "revision": row.revision, "customized": True})
