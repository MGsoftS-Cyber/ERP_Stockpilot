# Teaching edition: Verify business behavior using isolated test data.
import pytest
from rest_framework.test import APIClient

from apps.tenancy.models import Membership, Organization, User


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def organization_a(db) -> Organization:
    return Organization.objects.create(name="Organization A", slug="organization-a")


@pytest.fixture
def organization_b(db) -> Organization:
    return Organization.objects.create(name="Organization B", slug="organization-b")


@pytest.fixture
def admin_user(db) -> User:
    return User.objects.create_user(email="admin@example.com", password="StrongPass123!")


@pytest.fixture
def viewer_user(db) -> User:
    return User.objects.create_user(email="viewer@example.com", password="StrongPass123!")


@pytest.fixture
def admin_membership(admin_user, organization_a) -> Membership:
    return Membership.objects.create(
        user=admin_user,
        organization=organization_a,
        role=Membership.Role.ADMINISTRATOR,
    )


@pytest.fixture
def viewer_membership(viewer_user, organization_a) -> Membership:
    return Membership.objects.create(
        user=viewer_user,
        organization=organization_a,
        role=Membership.Role.VIEWER,
    )
