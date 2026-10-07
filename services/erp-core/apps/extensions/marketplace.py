# Publishing boundary: administrators submit a manifest; platform staff approve or reject it.
# Publisher namespace ownership prevents another organization from claiming the same plugin ID.
# Approved releases become catalog data used by registry.py and installation services.
"""Reviewed, declarative add-ons. No uploaded code is imported or executed."""

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record
from apps.common.commands import Conflict
from apps.extensions import registry
from apps.extensions.models import Installation, MarketplaceRelease
from apps.tenancy.models import Organization
from apps.tenancy.services import get_request_membership


def administrator(request):
    member = get_request_membership(request)
    if member.role != "ADMINISTRATOR":
        raise PermissionDenied("Organization administrator required")
    return member


class SubmissionSerializer(serializers.Serializer):
    manifest = serializers.JSONField()
    summary = serializers.CharField(max_length=240)

    def validate_manifest(self, value):
        return registry.validate(value)


class ReleaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = MarketplaceRelease
        fields = [
            "id",
            "slug",
            "version",
            "manifest",
            "checksum",
            "summary",
            "status",
            "review_note",
            "created_at",
        ]


class ReviewSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=["approved", "rejected"])
    note = serializers.CharField(max_length=500, allow_blank=True, default="")


class Marketplace(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        member = get_request_membership(request)
        installed = {
            x.slug: x for x in Installation.objects.filter(organization=member.organization)
        }
        community = {
            (x.slug, x.version): x for x in MarketplaceRelease.objects.filter(status="approved")
        }
        result = []
        for item in registry.releases():
            manifest = item["manifest"]
            row = installed.get(manifest["id"])
            publication = community.get((manifest["id"], manifest["version"]))
            result.append(
                item
                | {
                    "summary": publication.summary if publication else manifest["name"],
                    "publisher": "Reviewed community" if publication else "StockPilot",
                    "category": "Inventory"
                    if manifest["hook"] == "inventory.low_stock"
                    else "Workspace",
                    "installed_version": row.release["version"] if row else None,
                    "revision": row.revision if row else 0,
                    "update_available": bool(
                        row
                        and registry.version(manifest["version"])
                        > registry.version(row.release["version"])
                    ),
                }
            )
        return Response(
            {
                "results": result,
                "can_review": bool(request.user.is_staff and member.role == "ADMINISTRATOR"),
            }
        )


class Submissions(APIView):
    @extend_schema(responses=ReleaseSerializer(many=True))
    def get(self, request):
        member = administrator(request)
        rows = MarketplaceRelease.objects.all()
        if not request.user.is_staff:
            rows = rows.filter(organization=member.organization)
        return Response(ReleaseSerializer(rows.order_by("-created_at")[:100], many=True).data)

    @extend_schema(request=SubmissionSerializer, responses=ReleaseSerializer)
    @transaction.atomic
    def post(self, request):
        member = administrator(request)
        data = SubmissionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        manifest = data.validated_data["manifest"]
        if any(x["manifest"]["id"] == manifest["id"] for x in registry.bundled_releases()):
            raise ValidationError("This plugin ID is reserved by StockPilot")
        # A shared database lock serializes first claims to a publisher namespace.
        Organization.objects.select_for_update().order_by("pk").first()
        owner = MarketplaceRelease.objects.filter(slug=manifest["id"]).first()
        if owner and owner.organization_id != member.organization_id:
            raise PermissionDenied("This plugin ID belongs to another publisher")
        try:
            with transaction.atomic():
                row = MarketplaceRelease.objects.create(
                    organization=member.organization,
                    created_by=request.user,
                    slug=manifest["id"],
                    version=manifest["version"],
                    manifest=manifest,
                    checksum=registry.checksum(manifest),
                    summary=data.validated_data["summary"],
                )
        except IntegrityError as exc:
            raise Conflict("This release already exists; publish a new version") from exc
        record(member.organization, request.user, "marketplace.submit", row)
        return Response(ReleaseSerializer(row).data, status=201)


class Review(APIView):
    @extend_schema(request=ReviewSerializer, responses=ReleaseSerializer)
    @transaction.atomic
    def post(self, request, pk):
        administrator(request)
        if not request.user.is_staff:
            raise PermissionDenied("Platform reviewer required")
        data = ReviewSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        row = get_object_or_404(MarketplaceRelease.objects.select_for_update(), pk=pk)
        if row.status != "pending":
            raise Conflict("This release has already been reviewed")
        registry.validate(row.manifest)
        if registry.checksum(row.manifest) != row.checksum:
            raise ValidationError("Manifest integrity check failed")
        row.status = data.validated_data["decision"]
        row.review_note = data.validated_data["note"]
        row.reviewed_by = request.user
        row.save()
        record(row.organization, request.user, "marketplace.review", row, decision=row.status)
        return Response(ReleaseSerializer(row).data)
