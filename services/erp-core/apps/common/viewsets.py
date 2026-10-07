# DRF CRUD boundary: inherited views filter organization-owned records before retrieval.
# Serializers validate REST input; perform_create assigns tenant and creator from the checked
# request.
# Constraint conflicts and protected deletion return readable API errors instead of server failures.
# Teaching edition: Reuse tenant filtering and server-assigned fields across CRUD APIs.
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from apps.common.commands import Conflict
from apps.common.permissions import TenantRolePermission
from apps.tenancy.services import get_request_membership


class OrganizationScopedModelViewSet(viewsets.ModelViewSet):
    """Reusable, deny-by-default boundary for organization-owned API resources."""

    permission_classes = [IsAuthenticated, TenantRolePermission]

    # Resolve the active user membership for the selected organization.
    def get_membership(self):
        return get_request_membership(self.request)

    # Filter the base query before list/detail objects can be retrieved.
    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return super().get_queryset().none()
        membership = self.get_membership()
        return super().get_queryset().for_organization(membership.organization)

    # Assign tenant and creator from the request, never from client JSON.
    def perform_create(self, serializer) -> None:
        membership = self.get_membership()
        try:
            with transaction.atomic():
                serializer.save(organization=membership.organization, created_by=self.request.user)
        except IntegrityError as exc:
            raise Conflict("A record already exists or violates a database constraint.") from exc

    def perform_update(self, serializer):
        try:
            with transaction.atomic():
                serializer.save()
        except IntegrityError as exc:
            raise Conflict("A record already exists or violates a database constraint.") from exc

    def perform_destroy(self, instance):
        try:
            with transaction.atomic():
                instance.delete()
        except ProtectedError as exc:
            raise Conflict("This record is in use and cannot be deleted.") from exc
