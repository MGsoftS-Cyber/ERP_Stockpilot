"""Tenant-scoped plugin APIs. Catalog files are never uploaded/executed by API callers."""

from django.urls import path
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.extensions import hooks, registry
from apps.extensions.appearance import AppearanceView
from apps.extensions.marketplace import Marketplace, Review, Submissions
from apps.extensions.models import Installation, Revision
from apps.extensions.services import change
from apps.tenancy.services import get_request_membership


class CommandSerializer(serializers.Serializer):
    slug = serializers.SlugField(max_length=64)
    operation = serializers.ChoiceField(
        choices=["install", "update", "enable", "disable", "configure", "rollback"]
    )
    expected_revision = serializers.IntegerField(min_value=0)
    idempotency_key = serializers.UUIDField()
    version = serializers.CharField(required=False, max_length=20)
    target_revision = serializers.IntegerField(required=False, min_value=1)
    configuration = serializers.JSONField(required=False)

    def validate(self, attrs):
        operation = attrs["operation"]
        required = {
            "install": "version",
            "update": "version",
            "rollback": "target_revision",
            "configure": "configuration",
        }.get(operation)
        if required and required not in attrs:
            raise serializers.ValidationError({required: "Required for this operation"})
        if "configuration" in attrs and operation not in {"install", "configure", "update"}:
            raise serializers.ValidationError("This operation restores/preserves configuration")
        return attrs


class InstallationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Installation
        fields = ["id", "slug", "release", "checksum", "configuration", "enabled", "revision"]


class RevisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Revision
        fields = ["number", "operation", "snapshot", "created_at", "created_by"]


class PluginList(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        member = get_request_membership(request)
        return Response(
            {
                "catalog": registry.releases(),
                "installed": InstallationSerializer(
                    Installation.objects.filter(organization=member.organization).order_by("slug"),
                    many=True,
                ).data,
            }
        )


class PluginCommand(APIView):
    @extend_schema(request=CommandSerializer, responses=RevisionSerializer)
    def post(self, request):
        member = get_request_membership(request)
        serializer = CommandSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        revision = change(
            organization=member.organization, actor=request.user, command=serializer.validated_data
        )
        return Response(RevisionSerializer(revision).data)


class PluginHistory(APIView):
    @extend_schema(responses=RevisionSerializer(many=True))
    def get(self, request, slug):
        member = get_request_membership(request)
        # Latest 100 revisions shown; an older known revision can still be rolled back.
        history = Revision.objects.filter(
            organization=member.organization, installation__slug=slug
        )[:100]
        return Response(RevisionSerializer(history, many=True).data)


class PluginInsights(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        member = get_request_membership(request)
        result = []
        for plugin in Installation.objects.filter(organization=member.organization, enabled=True):
            try:
                registry.validate(plugin.release)
                registry.configuration(plugin.release, plugin.configuration)
                if registry.checksum(plugin.release) != plugin.checksum:
                    raise ValueError("Checksum mismatch")
                result.append(
                    {
                        "slug": plugin.slug,
                        "data": hooks.execute(
                            plugin.release, plugin.configuration, member.organization
                        ),
                    }
                )
            except Exception:
                # One broken hook does not suppress the other plugin cards or leak internals.
                result.append({"slug": plugin.slug, "error": "Plugin unavailable"})
        return Response({"results": result})


urlpatterns = [
    path("marketplace/", Marketplace.as_view()),
    path("submissions/", Submissions.as_view()),
    path("submissions/<uuid:pk>/review/", Review.as_view()),
    path("appearance/", AppearanceView.as_view()),
    path("", PluginList.as_view()),
    path("commands/", PluginCommand.as_view()),
    path("insights/", PluginInsights.as_view()),
    path("<slug:slug>/history/", PluginHistory.as_view()),
]
