"""Week 11: adversarial token, tenant, export and notification checks."""
import json
import time
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from django.core.management import call_command
from rest_framework.views import APIView

from apps.audit.models import AuditEvent
from apps.tenancy import oidc
from apps.tenancy.models import Membership

pytestmark = pytest.mark.django_db


@pytest.fixture
def signed_client(api_client, admin_user, admin_membership, monkeypatch, settings):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    settings.OIDC_ISSUER = "https://identity.test"
    settings.OIDC_JWKS_URL = "https://identity.test/oauth2/jwks"
    client = Mock()
    client.get_signing_key_from_jwt.return_value = SimpleNamespace(key=private.public_key())
    monkeypatch.setattr(oidc, "key_client", lambda _: client)
    monkeypatch.setattr(APIView, "authentication_classes", [oidc.SpringAuthentication])
    claims = {
        "iss": settings.OIDC_ISSUER, "aud": "stockpilot-api", "sub": str(admin_user.id),
        "exp": int(time.time()) + 300, "iat": int(time.time()), "scope": "openid erp",
        "token_use": "access",
        "org_roles": {str(admin_membership.organization_id): admin_membership.role},
    }

    def issue(overrides=None, key=None):
        payload = claims | (overrides or {})
        token = jwt.encode(payload, key or private, algorithm="RS256", headers={"kid": "test"})
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}",
                               HTTP_X_ORGANIZATION_ID=str(admin_membership.organization_id))
        return api_client
    return issue


def test_spring_uuid_and_memberships_survive_migration(signed_client, admin_user):
    response = signed_client({"scope": ["openid", "erp"]}).get("/api/v1/auth/me/")
    assert response.status_code == 200
    assert response.data["id"] == str(admin_user.id)
    assert len(response.data["memberships"]) == 1


@pytest.mark.parametrize("override", [
    {"aud": "different-api"}, {"iss": "https://attacker.test"}, {"exp": 1},
    {"token_use": "id"}, {"scope": "openid"}, {"sub": str(uuid4())},
    {"org_roles": []}, {"iat": int(time.time()) + 86400},
])
def test_reject_invalid_claims(signed_client, override):
    assert signed_client(override).get("/api/v1/auth/me/").status_code == 401


def test_reject_wrong_signature(signed_client):
    impostor = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert signed_client(key=impostor).get("/api/v1/auth/me/").status_code == 401


def test_role_mismatch_denied_instead_of_escalated(signed_client, organization_a):
    client = signed_client({"org_roles": {str(organization_a.id): "VIEWER"}})
    assert client.get("/api/v1/auth/me/").data["memberships"] == []
    assert client.get("/api/v1/notifications/revision/").status_code == 403


def test_revocation_takes_effect_without_waiting_for_token_expiry(signed_client, admin_membership):
    client = signed_client()
    Membership.objects.filter(pk=admin_membership.pk).update(is_active=False)
    assert client.get("/api/v1/notifications/revision/").status_code == 403


def test_notifications_hide_other_tenants(signed_client, organization_b):
    AuditEvent.objects.create(organization=organization_b, action="secret", entity_type="test",
                              entity_id=uuid4())
    client = signed_client()
    assert client.get("/api/v1/notifications/revision/").data == {"revision": None}
    client._credentials["HTTP_X_ORGANIZATION_ID"] = str(organization_b.id)
    assert client.get("/api/v1/notifications/revision/").status_code == 403


def test_notifications_are_bounded_query(signed_client, django_assert_num_queries):
    client = signed_client()
    # User, active grants, membership and indexed latest event: no per-event queries.
    with django_assert_num_queries(4):
        assert client.get("/api/v1/notifications/revision/").status_code == 200


def test_private_export_preserves_uuid_not_plaintext(admin_user, admin_membership, tmp_path):
    destination = tmp_path / "accounts.json"
    call_command("export_identity", str(destination))
    exported = json.loads(destination.read_text())
    assert destination.stat().st_mode & 0o777 == 0o600
    assert exported[0]["id"] == str(admin_user.id)
    assert exported[0]["password"].startswith("pbkdf2_sha256$")
    assert exported[0]["roles"][str(admin_membership.organization_id)] == admin_membership.role
