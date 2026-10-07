# Teaching edition: Verify business behavior using isolated test data.
"""Week 5 regression tests explain the business outcome each command must protect."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from django.db import close_old_connections, connection
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.catalog.models import Product, UnitOfMeasure
from apps.inventory.models import StockBalance, StockMovement, StockReservation, Warehouse
from apps.inventory.services import InventoryConflict, post_stock_adjustment, release_reservation
from apps.partners.models import BusinessPartner
from apps.sales.models import CustomerReturn, SalesOrder, Shipment
from apps.sales.services import cancel_order, confirm_order, return_goods, save_draft, ship_order
from apps.tenancy.models import Membership


@pytest.fixture
def sale(organization_a, admin_user, admin_membership):
    # Ten units are ordered against twenty-five available units.
    unit = UnitOfMeasure.objects.create(organization=organization_a, name="Each", symbol="ea")
    product = Product.objects.create(
        organization=organization_a, sku="W5", name="Mouse", unit=unit, purchase_price="20"
    )
    warehouse = Warehouse.objects.create(organization=organization_a, code="W5", name="Depot")
    customer = BusinessPartner.objects.create(
        organization=organization_a, code="CUS", name="Customer", partner_type="CUSTOMER"
    )
    args = dict(organization=organization_a, actor=admin_user)
    post_stock_adjustment(
        **args,
        warehouse=warehouse,
        reference="OPEN",
        reason="Test opening stock",
        idempotency_key=uuid.uuid4(),
        lines=[dict(product=product, quantity_signed=Decimal(25), unit_cost=Decimal(20))],
    )
    order = save_draft(
        **args,
        customer=customer,
        warehouse=warehouse,
        lines=[dict(product=product, quantity="10", unit_price="35")],
    )
    return args, order


def ship_payload(sale, quantity="4"):
    args, order = sale
    return dict(
        **args,
        order_id=order.pk,
        idempotency_key=uuid.uuid4(),
        lines=[dict(order_line=order.lines.get().pk, quantity=quantity)],
    )


def return_payload(sale, shipment, quantity="2"):
    args, _ = sale
    return dict(
        **args,
        shipment_id=shipment.pk,
        reason="Customer sent goods back",
        idempotency_key=uuid.uuid4(),
        lines=[dict(shipment_line=shipment.lines.get().pk, quantity=quantity)],
    )


@pytest.mark.django_db
def test_partial_full_shipment_and_return(sale):
    args, order = sale
    confirm_order(**args, order_id=order.pk)
    assert StockBalance.objects.get().reserved == 10
    shipment, _ = ship_order(**ship_payload(sale))
    balance = StockBalance.objects.get()
    assert (balance.on_hand, balance.reserved, balance.available) == (21, 6, 15)
    order.refresh_from_db()
    assert order.status == "PARTIALLY_SHIPPED"
    ship_order(**ship_payload(sale, "6"))
    order.refresh_from_db()
    assert order.status == "SHIPPED"
    assert StockReservation.objects.get().status == "FULFILLED"
    returned, created = return_goods(**return_payload(sale, shipment))
    assert created
    balance.refresh_from_db()
    assert (balance.on_hand, balance.reserved) == (17, 0)
    assert StockMovement.objects.get(source_id=returned.id).quantity_signed == 2
    order.refresh_from_db()
    assert order.status == "SHIPPED"  # A return must not reopen fulfilment.


@pytest.mark.django_db
def test_confirm_and_ship_retries_do_not_duplicate_stock(sale):
    args, order = sale
    confirm_order(**args, order_id=order.id)
    confirm_order(**args, order_id=order.id)
    assert StockReservation.objects.count() == 1
    payload = ship_payload(sale, "10")
    first, _ = ship_order(**payload)
    again, created = ship_order(**payload)
    assert again.id == first.id and not created
    assert StockBalance.objects.get().on_hand == 15
    payload["lines"][0]["quantity"] = "1"
    with pytest.raises(InventoryConflict):
        ship_order(**payload)


@pytest.mark.django_db
def test_return_replay_and_over_return(sale):
    args, order = sale
    confirm_order(**args, order_id=order.pk)
    shipment, _ = ship_order(**ship_payload(sale))
    payload = return_payload(sale, shipment, "4")
    first, _ = return_goods(**payload)
    replay, created = return_goods(**payload)
    assert not created and replay.id == first.id
    assert CustomerReturn.objects.count() == 1
    with pytest.raises(InventoryConflict):
        return_goods(**return_payload(sale, shipment, "1"))
    payload["reason"] = "Changed command"
    with pytest.raises(InventoryConflict):
        return_goods(**payload)


@pytest.mark.django_db
def test_cancel_partial_releases_only_remainder(sale):
    args, order = sale
    confirm_order(**args, order_id=order.pk)
    shipment, _ = ship_order(**ship_payload(sale))
    cancel_order(**args, order_id=order.pk, reason="Cancel remaining six")
    cancel_order(**args, order_id=order.pk, reason="Retry")
    balance = StockBalance.objects.get()
    assert (balance.on_hand, balance.reserved) == (21, 0)
    with pytest.raises(InventoryConflict):
        ship_order(**ship_payload(sale, "1"))
    # The already-delivered goods can still be returned after cancellation.
    return_goods(**return_payload(sale, shipment))
    assert StockBalance.objects.get().on_hand == 23


@pytest.mark.django_db
def test_manual_release_cannot_break_sales_reservation(sale):
    args, order = sale
    confirm_order(**args, order_id=order.pk)
    with pytest.raises(InventoryConflict):
        release_reservation(
            organization=args["organization"], reservation_id=order.lines.get().reservation_id
        )
    assert StockBalance.objects.get().reserved == 10


@pytest.mark.django_db
def test_multi_line_confirmation_rolls_back_when_any_product_is_short(sale):
    args, order = sale
    first = order.lines.get().product
    second = Product.objects.create(
        organization=args["organization"], sku="EMPTY", name="Empty", unit=first.unit
    )
    save_draft(
        **args,
        order_id=order.pk,
        customer=order.customer,
        warehouse=order.warehouse,
        lines=[
            dict(product=first, quantity="10", unit_price="35"),
            dict(product=second, quantity="1", unit_price="1"),
        ],
    )
    with pytest.raises(InventoryConflict):
        confirm_order(**args, order_id=order.pk)
    assert not StockReservation.objects.exists()
    assert StockBalance.objects.get(product=first).reserved == 0
    order.refresh_from_db()
    assert order.status == "DRAFT"


@pytest.mark.django_db
def test_ship_failure_rolls_back_document_balance_and_reservation(sale, monkeypatch):
    args, order = sale
    confirm_order(**args, order_id=order.pk)

    def fail(**kwargs):
        raise RuntimeError("Simulated ledger failure")

    monkeypatch.setattr("apps.inventory.fulfilment._post_movement", fail)
    with pytest.raises(RuntimeError):
        ship_order(**ship_payload(sale))
    assert not Shipment.objects.exists()
    assert StockBalance.objects.get().reserved == 10
    assert StockBalance.objects.get().on_hand == 25
    assert StockReservation.objects.get().fulfilled_quantity == 0
    assert order.lines.get().shipped_quantity == 0


@pytest.mark.django_db
@pytest.mark.parametrize("quantity", ["0", "-1", "NaN", "Infinity", "0.00001", "26"])
def test_invalid_ship_quantities_do_not_change_stock(sale, quantity):
    args, order = sale
    confirm_order(**args, order_id=order.pk)
    with pytest.raises((ValidationError, InventoryConflict)):
        ship_order(**ship_payload(sale, quantity))
    assert not Shipment.objects.exists()
    assert StockBalance.objects.get().on_hand == 25


@pytest.mark.django_db
def test_cross_tenant_and_noncustomer_rejected(sale, organization_b):
    args, order = sale
    product = order.lines.get().product
    foreign = Warehouse.objects.create(organization=organization_b, code="X", name="Foreign")
    with pytest.raises(ValidationError):
        save_draft(
            **args,
            customer=order.customer,
            warehouse=foreign,
            lines=[dict(product=product, quantity="1", unit_price="2")],
        )
    order.customer.partner_type = "SUPPLIER"
    order.customer.save()
    with pytest.raises(ValidationError):
        save_draft(
            **args,
            customer=order.customer,
            warehouse=order.warehouse,
            lines=[dict(product=product, quantity="1", unit_price="2")],
        )


@pytest.mark.django_db
def test_api_lifecycle_and_role_matrix(
    sale, api_client, viewer_user, viewer_membership, admin_membership
):
    args, order = sale
    headers = {"HTTP_X_ORGANIZATION_ID": str(args["organization"].pk)}
    api_client.force_authenticate(args["actor"])
    url = f"/api/v1/sales/orders/{order.pk}/"
    assert api_client.get(url, **headers).status_code == 200
    assert api_client.post(url + "ship/", {}, format="json", **headers).status_code == 400
    assert api_client.post(url + "confirm/", {}, format="json", **headers).status_code == 200
    payload = dict(
        idempotency_key=str(uuid.uuid4()),
        lines=[dict(order_line=str(order.lines.get().pk), quantity="4")],
    )
    shipped = api_client.post(url + "ship/", payload, format="json", **headers)
    assert shipped.status_code == 201
    assert api_client.post(url + "ship/", payload, format="json", **headers).status_code == 200
    return_url = f"/api/v1/sales/shipments/{shipped.data['id']}/return/"
    returned = api_client.post(
        return_url,
        dict(
            idempotency_key=str(uuid.uuid4()),
            reason="Test",
            lines=[dict(shipment_line=shipped.data["lines"][0]["id"], quantity="1")],
        ),
        format="json",
        **headers,
    )
    assert returned.status_code == 201
    # Sales agents can confirm/cancel but cannot perform physical stock operations.
    admin_membership.role = Membership.Role.SALES_AGENT
    admin_membership.save()
    assert api_client.post(url + "ship/", payload, format="json", **headers).status_code == 403
    api_client.force_authenticate(viewer_user)
    assert api_client.get(url, **headers).status_code == 200
    assert (
        api_client.post(url + "cancel/", {"reason": "x"}, format="json", **headers).status_code
        == 403
    )


@pytest.mark.django_db
def test_foreign_tenant_cannot_read_order(sale, api_client, organization_b):
    args, order = sale
    Membership.objects.create(user=args["actor"], organization=organization_b, role="ADMINISTRATOR")
    api_client.force_authenticate(args["actor"])
    headers = {"HTTP_X_ORGANIZATION_ID": str(organization_b.pk)}
    assert api_client.get("/api/v1/sales/orders/", **headers).data["count"] == 0
    assert api_client.get(f"/api/v1/sales/orders/{order.pk}/", **headers).status_code == 404
    assert (
        api_client.post(
            f"/api/v1/sales/orders/{order.pk}/confirm/", {}, format="json", **headers
        ).status_code
        == 404
    )


@pytest.mark.django_db
def test_inactive_membership_blocks_service(sale, admin_membership):
    args, order = sale
    admin_membership.is_active = False
    admin_membership.save()
    with pytest.raises(PermissionDenied):
        confirm_order(**args, order_id=order.pk)


@pytest.mark.django_db(transaction=True)
def test_concurrent_shipments_post_once(sale):
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row locks.")
    args, order = sale
    confirm_order(**args, order_id=order.pk)
    payload = ship_payload(sale, "10")

    def worker():
        close_old_connections()
        try:
            return ship_order(**payload)[1]
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: worker(), range(2))) == [False, True]
    assert Shipment.objects.count() == 1
    assert StockBalance.objects.get().on_hand == 15


@pytest.mark.django_db
def test_api_draft_create_revise_and_reservation_ownership(sale, api_client):
    args, order = sale
    api_client.force_authenticate(args["actor"])
    headers = {"HTTP_X_ORGANIZATION_ID": str(args["organization"].pk)}
    data = dict(
        customer=str(order.customer_id),
        warehouse=str(order.warehouse_id),
        lines=[dict(product=str(order.lines.get().product_id), quantity="3", unit_price="2")],
    )
    response = api_client.post("/api/v1/sales/orders/", data, format="json", **headers)
    assert response.status_code == 201
    url = f"/api/v1/sales/orders/{response.data['id']}/"
    data["lines"][0]["quantity"] = "5"
    assert api_client.post(url + "revise/", data, format="json", **headers).status_code == 200
    assert api_client.post(url + "confirm/", {}, format="json", **headers).status_code == 200
    assert api_client.post(url + "revise/", data, format="json", **headers).status_code == 409
    reservation = SalesOrder.objects.get(pk=response.data["id"]).lines.get().reservation
    release_url = f"/api/v1/inventory/stock-reservations/{reservation.pk}/release/"
    assert api_client.post(release_url, {}, format="json", **headers).status_code == 409
    # A caller cannot masquerade as the sales module through the manual reservation API.
    manual = dict(
        product=str(order.lines.get().product_id),
        warehouse=str(order.warehouse_id),
        quantity="1",
        source_type="SALES_ORDER",
        source_id=str(order.pk),
        idempotency_key=str(uuid.uuid4()),
    )
    assert (
        api_client.post(
            "/api/v1/inventory/stock-reservations/", manual, format="json", **headers
        ).status_code
        == 400
    )


@pytest.mark.django_db
def test_wrong_document_lines_are_rejected(sale):
    args, order = sale
    confirm_order(**args, order_id=order.pk)
    bad = ship_payload(sale)
    bad["lines"][0]["order_line"] = uuid.uuid4()
    with pytest.raises(InventoryConflict):
        ship_order(**bad)
    shipment, _ = ship_order(**ship_payload(sale))
    bad_return = return_payload(sale, shipment)
    bad_return["lines"][0]["shipment_line"] = uuid.uuid4()
    with pytest.raises(InventoryConflict):
        return_goods(**bad_return)
    assert not CustomerReturn.objects.exists()


@pytest.mark.django_db
def test_whole_unit_and_inactive_partner_are_revalidated(sale):
    args, order = sale
    product = order.lines.get().product
    product.unit.allows_decimals = False
    product.unit.save()
    with pytest.raises(ValidationError):
        save_draft(
            **args,
            customer=order.customer,
            warehouse=order.warehouse,
            lines=[dict(product=product, quantity="1.5", unit_price="1")],
        )
    order.customer.partner_type = "SUPPLIER"
    order.customer.save()
    with pytest.raises(ValidationError):
        confirm_order(**args, order_id=order.pk)
    assert not StockReservation.objects.exists()


@pytest.mark.django_db
def test_return_failure_rolls_back_return_counter_and_stock(sale, monkeypatch):
    args, order = sale
    confirm_order(**args, order_id=order.pk)
    shipment, _ = ship_order(**ship_payload(sale))

    def fail(**kwargs):
        raise RuntimeError("Simulated return inventory failure")

    monkeypatch.setattr("apps.sales.services.post_customer_return", fail)
    with pytest.raises(RuntimeError):
        return_goods(**return_payload(sale, shipment))
    assert not CustomerReturn.objects.exists()
    assert shipment.lines.get().returned_quantity == 0
    assert StockBalance.objects.get().on_hand == 21
