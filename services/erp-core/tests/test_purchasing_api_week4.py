# Teaching edition: Verify business behavior using isolated test data.
import uuid

import pytest

from apps.catalog.models import Product, UnitOfMeasure
from apps.inventory.models import StockMovement, Warehouse
from apps.partners.models import BusinessPartner
from apps.tenancy.models import Membership


@pytest.mark.django_db
def test_full_api_workflow(api_client, admin_user, admin_membership, organization_a):
    org = organization_a
    api_client.force_authenticate(admin_user)
    headers = {"HTTP_X_ORGANIZATION_ID": str(org.id)}
    root = "/api/v1/purchasing/orders/"
    unit = UnitOfMeasure.objects.create(organization=org, name="Each", symbol="ea")
    product = Product.objects.create(organization=org, sku="API", name="Part", unit=unit)
    supplier = BusinessPartner.objects.create(
        organization=org, code="S", name="Supplier", partner_type="SUPPLIER"
    )
    warehouse = Warehouse.objects.create(organization=org, code="W", name="Warehouse")
    draft = api_client.post(
        root,
        {
            "supplier": str(supplier.id),
            "lines": [
                {"product": str(product.id), "quantity": "2", "unit_price": "10"},
            ],
        },
        format="json",
        **headers,
    )
    assert draft.status_code == 201, draft.data
    url = f"{root}{draft.data['id']}/"
    for action in ("submit", "approve"):
        response = api_client.post(
            url + "transition/", {"action": action}, format="json", **headers
        )
        assert response.status_code == 200, response.data
    payload = {
        "warehouse": str(warehouse.id),
        "idempotency_key": str(uuid.uuid4()),
        "lines": [{"order_line": draft.data["lines"][0]["id"], "quantity": "2"}],
    }
    response = api_client.post(url + "receive/", payload, format="json", **headers)
    assert response.status_code == 201, response.data
    assert api_client.post(url + "receive/", payload, format="json", **headers).status_code == 200
    assert StockMovement.objects.count() == 1
    assert api_client.get(url, **headers).data["status"] == "RECEIVED"
    assert api_client.get("/api/v1/purchasing/receipts/", **headers).data["count"] == 1


@pytest.mark.django_db
def test_buyer_cannot_approve(api_client, admin_user, admin_membership, organization_a):
    from apps.purchasing.models import PurchaseOrder

    supplier = BusinessPartner.objects.create(
        organization=organization_a, code="S", name="Supplier", partner_type="SUPPLIER"
    )
    order = PurchaseOrder.objects.create(
        organization=organization_a, supplier=supplier, reference="PO-TEST", status="SUBMITTED"
    )
    admin_membership.role = Membership.Role.PURCHASING_AGENT
    admin_membership.save()
    api_client.force_authenticate(admin_user)
    response = api_client.post(
        f"/api/v1/purchasing/orders/{order.id}/transition/",
        {"action": "approve"},
        format="json",
        HTTP_X_ORGANIZATION_ID=str(organization_a.id),
    )
    assert response.status_code == 403
