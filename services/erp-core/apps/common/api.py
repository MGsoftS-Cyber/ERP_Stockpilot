"""New modules share tenant scoping, but every write stays in a business service."""

from rest_framework import serializers, viewsets
from rest_framework.permissions import IsAuthenticated

from apps.common.commands import FINANCE_ROLES
from apps.common.permissions import TenantRolePermission
from apps.tenancy.services import get_request_membership


class TenantReadViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated, TenantRolePermission]
    write_roles = FINANCE_ROLES

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset.none()
        return self.queryset.filter(organization=get_request_membership(self.request).organization)

    def command_args(self):
        return {
            "organization": get_request_membership(self.request).organization,
            "actor": self.request.user,
        }

    def validate(self, cls):
        serializer = cls(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data


class EmptyInput(serializers.Serializer):
    pass


class ReasonInput(serializers.Serializer):
    reason = serializers.CharField(max_length=2000)


class CurrencyInput(serializers.Serializer):
    currency = serializers.ChoiceField(choices=["DZD", "EUR", "USD"], default="DZD")
