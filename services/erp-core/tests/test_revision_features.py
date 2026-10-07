"""Public API regressions for marketplace, appearance and malformed input."""

import sys
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest

from apps.extensions.appearance import DEFAULTS
from apps.extensions.models import MarketplaceRelease
from apps.extensions.registry import bundled_releases, checksum, validate
from apps.tenancy.models import Membership

pytestmark = pytest.mark.django_db


@pytest.fixture
def client(api_client, admin_user, admin_membership, organization_a):
    api_client.force_authenticate(admin_user)
    api_client.credentials(HTTP_X_ORGANIZATION_ID=str(organization_a.id))
    return api_client


def manifest():
    data = deepcopy(bundled_releases()[0]["manifest"])
    data.update(
        id="community-alert", requires={}, hook="inventory.low_stock", settings={"threshold": 8}
    )
    return data


def test_submit_review_install_and_publisher_isolation(client, admin_user, organization_b):
    data = manifest()
    response = client.post(
        "/api/v1/plugins/submissions/",
        {"manifest": data, "summary": "Community alerts"},
        format="json",
    )
    assert response.status_code == 201
    pk = response.data["id"]
    route = f"/api/v1/plugins/submissions/{pk}/review/"
    assert all(
        x["manifest"]["id"] != data["id"]
        for x in client.get("/api/v1/plugins/marketplace/").data["results"]
    )
    assert client.post(route, {"decision": "approved"}, format="json").status_code == 403
    admin_user.is_staff = True
    admin_user.save()
    assert client.post(route, {"decision": "approved"}, format="json").status_code == 200
    assert client.post(route, {"decision": "rejected"}, format="json").status_code == 409
    Membership.objects.create(user=admin_user, organization=organization_b, role="ADMINISTRATOR")
    client.credentials(HTTP_X_ORGANIZATION_ID=str(organization_b.id))
    response = client.post(
        "/api/v1/plugins/commands/",
        {
            "slug": data["id"],
            "operation": "install",
            "version": data["version"],
            "expected_revision": 0,
            "idempotency_key": str(uuid4()),
        },
        format="json",
    )
    assert response.status_code == 200
    data["version"] = "2.0.0"
    assert (
        client.post(
            "/api/v1/plugins/submissions/", {"manifest": data, "summary": "Hijack"}, format="json"
        ).status_code
        == 403
    )
    admin_user.is_staff = False
    admin_user.save()
    assert client.get("/api/v1/plugins/submissions/").data == []


@pytest.mark.parametrize(
    "patch",
    [
        {"hook": []},
        {"hook": {}},
        {"api": True},
        {"requires": {"other": 1}},
        {"settings": {"threshold": True}},
    ],
)
def test_invalid_manifest_returns_400_not_500(client, patch):
    assert (
        client.post(
            "/api/v1/plugins/submissions/",
            {"manifest": manifest() | patch, "summary": "Invalid"},
            format="json",
        ).status_code
        == 400
    )
    assert not MarketplaceRelease.objects.exists()


def test_duplicate_release_and_reserved_namespace(client):
    data = {"manifest": manifest(), "summary": "Example"}
    assert client.post("/api/v1/plugins/submissions/", data, format="json").status_code == 201
    assert client.post("/api/v1/plugins/submissions/", data, format="json").status_code == 409
    data["manifest"]["id"] = "stock-alerts"
    assert client.post("/api/v1/plugins/submissions/", data, format="json").status_code == 400


def test_design_default_revision_permissions_and_isolation(
    client, viewer_user, viewer_membership, organization_b
):
    url = "/api/v1/plugins/appearance/"
    response = client.get(url)
    assert response.data == {"settings": DEFAULTS, "revision": 0, "customized": False}
    payload = {"settings": DEFAULTS | {"primary": "#123456"}, "expected_revision": 0}
    assert client.put(url, payload, format="json").status_code == 200
    assert client.put(url, payload, format="json").status_code == 409
    client.force_authenticate(viewer_user)
    assert client.get(url).data["settings"]["primary"] == "#123456"
    assert client.put(url, payload, format="json").status_code == 403
    client.credentials(HTTP_X_ORGANIZATION_ID=str(organization_b.id))
    assert client.get(url).status_code == 403


@pytest.mark.parametrize(
    "patch",
    [
        {"primary": "url(evil)"},
        {"radius": -1},
        {"font_size": 100},
        {"mode": "unknown"},
        {"density": "unknown"},
    ],
)
def test_design_rejects_unsafe_or_invalid_values(client, patch):
    assert (
        client.put(
            "/api/v1/plugins/appearance/",
            {"settings": DEFAULTS | patch, "expected_revision": 0},
            format="json",
        ).status_code
        == 400
    )


@pytest.mark.parametrize("language", ["en", "fr", "ar"])
def test_language_header_preserves_api_contract(client, language):
    response = client.get("/api/v1/plugins/marketplace/", HTTP_ACCEPT_LANGUAGE=language)
    assert response.status_code == 200 and "results" in response.data
    assert response["Content-Language"] == language


def test_sdk_contract_parity():
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "sdk" / "python"))
    from stockpilot_validation import checksum as sdk_checksum
    from stockpilot_validation import validate as sdk_validate

    assert sdk_validate(manifest()) == validate(manifest())
    assert sdk_checksum(manifest()) == checksum(manifest())
    with pytest.raises(ValueError):
        sdk_validate(manifest() | {"hook": []})


def test_master_data_duplicate_returns_conflict(client):
    url = "/api/v1/catalog/categories/"
    data = {"code": "SAME", "name": "Example"}
    assert client.post(url, data, format="json").status_code == 201
    assert client.post(url, data, format="json").status_code == 409


def test_protected_master_data_delete_returns_conflict(client, organization_a):
    from apps.catalog.models import Product, UnitOfMeasure

    unit = UnitOfMeasure.objects.create(organization=organization_a, name="Piece", symbol="pc")
    Product.objects.create(organization=organization_a, sku="TEST", name="Example", unit=unit)
    assert client.delete(f"/api/v1/catalog/units/{unit.pk}/").status_code == 409
    assert UnitOfMeasure.objects.filter(pk=unit.pk).exists()


@pytest.mark.parametrize(
    "endpoint",
    [
        "catalog/products",
        "catalog/categories",
        "catalog/units",
        "catalog/tax-rates",
        "partners/business-partners",
        "inventory/warehouses",
        "inventory/stock-balances",
        "inventory/stock-movements",
        "inventory/stock-reservations",
        "purchasing/orders",
        "sales/orders",
        "billing/invoices",
        "billing/payments",
        "finance/expenses",
        "audit/events",
        "intelligence/documents",
        "intelligence/forecasts",
        "plugins",
        "plugins/insights",
        "plugins/marketplace",
        "plugins/submissions",
        "plugins/appearance",
    ],
)
def test_dashboard_routes_serialize_json(client, endpoint):
    response = client.get(f"/api/v1/{endpoint}/")
    assert response.status_code == 200, (endpoint, response.data)
    assert isinstance(response.json(), (dict, list))
