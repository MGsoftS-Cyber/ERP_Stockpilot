# Teaching edition: Convert records to JSON and validate incoming API values.
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.tenancy.models import Membership, Organization, User


class StockPilotTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user: User):
        token = super().get_token(user)
        token["email"] = user.email
        return token


class OrganizationSerializer(serializers.ModelSerializer):
    # Django metadata: schema or API options, not a constructor.
    class Meta:
        model = Organization
        fields = ["id", "name", "slug", "is_active"]


class MembershipSerializer(serializers.ModelSerializer):
    organization = OrganizationSerializer(read_only=True)
    role_label = serializers.CharField(source="get_role_display", read_only=True)

    # Django metadata: schema or API options, not a constructor.
    class Meta:
        model = Membership
        fields = ["id", "organization", "role", "role_label", "is_active"]


class CurrentUserSerializer(serializers.ModelSerializer):
    memberships = serializers.SerializerMethodField()

    # Django metadata: schema or API options, not a constructor.
    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "memberships"]

    @extend_schema_field(MembershipSerializer(many=True))
    def get_memberships(self, user: User):
        memberships = user.memberships.filter(
            is_active=True,
            organization__is_active=True,
        ).select_related("organization")
        grants = getattr(user, "oidc_org_roles", None)
        if grants is not None:
            memberships = [m for m in memberships
                           if grants.get(str(m.organization_id)) == m.role]
        return MembershipSerializer(memberships, many=True).data
