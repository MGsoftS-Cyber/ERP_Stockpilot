# Teaching edition: Handle HTTP requests and delegate validation and business work.
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.tenancy.api.serializers import (
    CurrentUserSerializer,
    OrganizationSerializer,
    StockPilotTokenObtainPairSerializer,
)
from apps.tenancy.models import Organization


class StockPilotTokenObtainPairView(TokenObtainPairView):
    serializer_class = StockPilotTokenObtainPairSerializer


class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=CurrentUserSerializer)
    def get(self, request) -> Response:
        serializer = CurrentUserSerializer(request.user)
        return Response(serializer.data)


class OrganizationViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = OrganizationSerializer
    permission_classes = [IsAuthenticated]

    # Filter the base query before list/detail objects can be retrieved.
    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Organization.objects.none()
        grants = getattr(self.request.user, "oidc_org_roles", None)
        if grants is not None:
            return Organization.objects.filter(id__in=grants, is_active=True)
        if self.request.user.is_superuser:
            return Organization.objects.filter(is_active=True)
        return Organization.objects.filter(
            memberships__user=self.request.user,
            memberships__is_active=True,
            is_active=True,
        ).distinct()
