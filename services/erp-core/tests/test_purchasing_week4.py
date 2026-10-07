# Teaching edition: Verify business behavior using isolated test data.
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from django.db import close_old_connections, connection
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.catalog.models import Product, UnitOfMeasure
from apps.inventory.models import StockBalance, StockMovement, Warehouse
from apps.inventory.services import InventoryConflict
from apps.partners.models import BusinessPartner
from apps.purchasing.models import GoodsReceipt
from apps.purchasing.services import create_order, receive_goods, revise_order, transition_order


@pytest.fixture
def purchase(organization_a, admin_user, admin_membership):
    unit = UnitOfMeasure.objects.create(organization=organization_a, name="Each", symbol="ea")
    product = Product.objects.create(organization=organization_a, sku="W4", name="Part", unit=unit)
    warehouse = Warehouse.objects.create(organization=organization_a, code="W4", name="Depot")
    supplier = BusinessPartner.objects.create(
        organization=organization_a, code="SUP", name="Supplier", partner_type="SUPPLIER"
    )
    args = dict(organization=organization_a, actor=admin_user)
    order = create_order(
        **args,
        supplier=supplier,
        lines=[{"product": product, "quantity": "10", "unit_price": "2.5000"}],
    )
    return args, order, warehouse


def approve(args, order):
    transition_order(**args, order_id=order.id, action="submit")
    transition_order(**args, order_id=order.id, action="approve")


def receipt_args(purchase, quantity="4", key=None):
    args, order, warehouse = purchase
    return dict(
        **args,
        order_id=order.id,
        warehouse=warehouse,
        idempotency_key=key or uuid.uuid4(),
        lines=[{"order_line": order.lines.get().id, "quantity": quantity}],
    )


@pytest.mark.django_db
def test_partial_then_complete_receipt(purchase):
    args, order, _ = purchase
    approve(args, order)
    receipt, created = receive_goods(**receipt_args(purchase))
    assert created
    order.refresh_from_db()
    assert order.status == "PARTIALLY_RECEIVED"
    assert StockMovement.objects.get(source_id=receipt.id).quantity_signed == Decimal("4")
    assert StockBalance.objects.get().on_hand == Decimal("4")
    receive_goods(**receipt_args(purchase, "6"))
    order.refresh_from_db()
    assert order.status == "RECEIVED"
    assert StockBalance.objects.get().on_hand == Decimal("10")
    transition_order(**args, order_id=order.id, action="close", reason="Reviewed quantities")
    order.refresh_from_db()
    assert order.status == "CLOSED"


@pytest.mark.django_db
def test_receipt_replay_and_changed_payload(purchase):
    args, order, _ = purchase
    approve(args, order)
    payload = receipt_args(purchase, "10")
    first, _ = receive_goods(**payload)
    second, created = receive_goods(**payload)
    assert not created and first.pk == second.pk
    assert StockMovement.objects.count() == 1
    payload["lines"][0]["quantity"] = "1"
    with pytest.raises(InventoryConflict):
        receive_goods(**payload)


@pytest.mark.django_db
def test_over_receipt_has_no_side_effects(purchase):
    args, order, _ = purchase
    approve(args, order)
    with pytest.raises(InventoryConflict):
        receive_goods(**receipt_args(purchase, "11"))
    assert not GoodsReceipt.objects.exists()
    assert not StockMovement.objects.exists()
    assert order.lines.get().received_quantity == 0


@pytest.mark.django_db
def test_receipt_requires_approval(purchase):
    with pytest.raises(InventoryConflict):
        receive_goods(**receipt_args(purchase))


@pytest.mark.django_db
def test_viewer_forbidden(purchase, viewer_user, viewer_membership):
    payload = receipt_args(purchase)
    payload["actor"] = viewer_user
    with pytest.raises(PermissionDenied):
        receive_goods(**payload)


@pytest.mark.django_db
def test_cross_tenant_warehouse_rejected(purchase, organization_b):
    payload = receipt_args(purchase)
    payload["warehouse"] = Warehouse.objects.create(
        organization=organization_b, code="OTHER", name="Other"
    )
    with pytest.raises(ValidationError):
        receive_goods(**payload)


@pytest.mark.django_db
def test_foreign_line_rejected(purchase):
    args, order, _ = purchase
    approve(args, order)
    payload = receipt_args(purchase)
    payload["lines"][0]["order_line"] = uuid.uuid4()
    with pytest.raises(ValidationError):
        receive_goods(**payload)
    assert GoodsReceipt.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize("quantity", ["0", "-1", "NaN", "0.00001"])
def test_bad_receipt_decimal(purchase, quantity):
    with pytest.raises(ValidationError):
        receive_goods(**receipt_args(purchase, quantity))


@pytest.mark.django_db
def test_cancel_after_partial_is_rejected(purchase):
    args, order, _ = purchase
    approve(args, order)
    receive_goods(**receipt_args(purchase))
    with pytest.raises(InventoryConflict):
        transition_order(**args, order_id=order.id, action="cancel")


@pytest.mark.django_db
def test_correction_and_revision(purchase):
    args, order, _ = purchase
    transition_order(**args, order_id=order.id, action="submit")
    transition_order(**args, order_id=order.id, action="return_to_draft", reason="Wrong quantity")
    product = order.lines.get().product
    revise_order(
        **args,
        order_id=order.id,
        supplier=order.supplier,
        lines=[{"product": product, "quantity": "8", "unit_price": "3"}],
    )
    assert order.lines.get().quantity == 8
    approve(args, order)
    with pytest.raises(InventoryConflict):
        revise_order(
            **args,
            order_id=order.id,
            supplier=order.supplier,
            lines=[{"product": product, "quantity": "9", "unit_price": "3"}],
        )


@pytest.mark.django_db
def test_api_tenant_filter_and_viewer_write(
    purchase, api_client, viewer_user, viewer_membership, organization_b, admin_user
):
    args, order, _ = purchase
    api_client.force_authenticate(viewer_user)
    headers = {"HTTP_X_ORGANIZATION_ID": str(args["organization"].id)}
    url = "/api/v1/purchasing/orders/"
    assert api_client.get(url, **headers).data["count"] == 1
    assert api_client.post(url, {}, format="json", **headers).status_code == 403
    api_client.force_authenticate(admin_user)
    assert api_client.get(url, HTTP_X_ORGANIZATION_ID=str(organization_b.id)).status_code == 403
    assert api_client.patch(f"{url}{order.id}/", {}, format="json", **headers).status_code == 405


@pytest.mark.django_db
def test_receipt_transaction_rolls_back_on_posting_failure(purchase, monkeypatch):
    args, order, _ = purchase
    approve(args, order)

    def fail(**kwargs):
        raise RuntimeError("Simulated inventory failure")

    monkeypatch.setattr("apps.purchasing.services.post_purchase_receipt_movement", fail)
    with pytest.raises(RuntimeError):
        receive_goods(**receipt_args(purchase))
    assert not GoodsReceipt.objects.exists()
    assert order.lines.get().received_quantity == 0
    order.refresh_from_db()
    assert order.status == "APPROVED"


@pytest.mark.django_db(transaction=True)
def test_concurrent_duplicate_receipts_post_once(purchase):
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row locks; run with DATABASE_URL set.")
    args, order, _ = purchase
    approve(args, order)
    payload = receipt_args(purchase, "10")

    def worker():
        close_old_connections()
        try:
            return receive_goods(**payload)[1]
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: worker(), range(2)))
    assert sorted(results) == [False, True]
    assert StockMovement.objects.count() == 1
