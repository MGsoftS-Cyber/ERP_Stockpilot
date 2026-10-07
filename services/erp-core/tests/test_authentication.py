# Teaching edition: Verify business behavior using isolated test data.
import pytest
from django.urls import reverse

from apps.tenancy.models import Membership


@pytest.mark.django_db
def test_openapi_schema_is_available(api_client):
    response = api_client.get("/api/schema/")

    assert response.status_code == 200


@pytest.mark.django_db
def test_jwt_login_and_current_user(
    api_client,
    admin_user,
    organization_a,
    admin_membership,
):
    token_response = api_client.post(
        reverse("token-obtain-pair"),
        {"email": "admin@example.com", "password": "StrongPass123!"},
        format="json",
    )

    assert token_response.status_code == 200
    assert "access" in token_response.data
    assert "refresh" in token_response.data

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token_response.data['access']}")
    user_response = api_client.get(reverse("current-user"))

    assert user_response.status_code == 200
    assert user_response.data["email"] == admin_user.email
    assert user_response.data["memberships"][0]["role"] == Membership.Role.ADMINISTRATOR
    assert user_response.data["memberships"][0]["organization"]["id"] == str(organization_a.id)


@pytest.mark.django_db
def test_organizations_endpoint_returns_only_memberships(
    api_client,
    admin_user,
    organization_a,
    organization_b,
    admin_membership,
):
    api_client.force_authenticate(admin_user)

    response = api_client.get("/api/v1/organizations/")

    assert response.status_code == 200
    returned_ids = {item["id"] for item in response.data["results"]}
    assert returned_ids == {str(organization_a.id)}
    assert str(organization_b.id) not in returned_ids
