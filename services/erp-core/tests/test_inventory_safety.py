import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from django.db import close_old_connections, connection
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.catalog.models import Product, UnitOfMeasure
from apps.inventory.models import StockBalance, StockMovement, StockReservation, Warehouse
from apps.inventory.services import (
    InventoryConflict,
    post_stock_adjustment,
    reserve_stock,
    transfer_stock,
)
from apps.partners.models import BusinessPartner
from apps.purchasing.services import create_order, receive_goods, transition_order


@pytest.fixture
def stock(organization_a, admin_user, admin_membership):
    unit = UnitOfMeasure.objects.create(
        organization=organization_a, name="Each", symbol="ea", allows_decimals=False
    )
    product = Product.objects.create(
        organization=organization_a, sku="SAFETY", name="Test product", unit=unit
    )
    source = Warehouse.objects.create(organization=organization_a, code="A", name="Source")
    target = Warehouse.objects.create(organization=organization_a, code="B", name="Target")
    args = {"organization": organization_a, "actor": admin_user}
    post_stock_adjustment(
        **args,
        warehouse=source,
        reason="Opening",
        idempotency_key=uuid.uuid4(),
        lines=[{"product": product, "quantity_signed": "10"}],
    )
    return args, product, source, target


@pytest.mark.parametrize("operation", ["adjust", "transfer", "reserve"])
def test_changed_inventory_retry_conflicts_without_side_effects(stock, operation):
    args, product, source, target = stock
    key = uuid.uuid4()
    if operation == "adjust":
        fn = post_stock_adjustment
        payload = dict(
            warehouse=source,
            reason="Count",
            idempotency_key=key,
            lines=[dict(product=product, quantity_signed="2")],
        )
        changed = {**payload, "lines": [dict(product=product, quantity_signed="3")]}
    elif operation == "transfer":
        fn = transfer_stock
        payload = dict(
            source_warehouse=source,
            destination_warehouse=target,
            idempotency_key=key,
            lines=[dict(product=product, quantity="2")],
        )
        changed = {**payload, "lines": [dict(product=product, quantity="3")]}
    else:
        fn = reserve_stock
        payload = dict(
            product=product,
            warehouse=source,
            quantity="2",
            source_type="MANUAL",
            source_id=uuid.uuid4(),
            idempotency_key=key,
        )
        changed = {**payload, "quantity": "3"}
    first, created = fn(**args, **payload)
    again, repeated = fn(**args, **payload)
    assert created and not repeated and first.pk == again.pk
    balances = list(
        StockBalance.objects.order_by("warehouse_id").values_list("on_hand", "reserved")
    )
    count = StockMovement.objects.count()
    with pytest.raises(InventoryConflict):
        fn(**args, **changed)
    assert count == StockMovement.objects.count()
    assert balances == list(
        StockBalance.objects.order_by("warehouse_id").values_list("on_hand", "reserved")
    )


def test_service_permissions_apply_before_idempotent_replay(stock, viewer_user, viewer_membership):
    args, product, source, _ = stock
    payload = dict(
        warehouse=source,
        reason="Count",
        idempotency_key=uuid.uuid4(),
        lines=[dict(product=product, quantity_signed="1")],
    )
    post_stock_adjustment(**args, **payload)
    with pytest.raises(PermissionDenied):
        post_stock_adjustment(**{**args, "actor": viewer_user}, **payload)
    args["actor"].is_active = False
    with pytest.raises(PermissionDenied):
        post_stock_adjustment(**args, **payload)


@pytest.mark.parametrize("value", ["0.5", "NaN", "Infinity", "0", "0.00001"])
def test_invalid_inventory_quantities_do_not_post(stock, value):
    args, product, source, _ = stock
    with pytest.raises(ValidationError):
        post_stock_adjustment(
            **args,
            warehouse=source,
            reason="Invalid",
            idempotency_key=uuid.uuid4(),
            lines=[dict(product=product, quantity_signed=value)],
        )
    assert StockBalance.objects.get().on_hand == Decimal("10")


def test_purchase_whole_unit_receipt_and_inactive_actor(stock):
    args, product, source, _ = stock
    partner = BusinessPartner.objects.create(
        organization=args["organization"], code="SUP", name="Supplier", partner_type="SUPPLIER"
    )
    payload = dict(supplier=partner, lines=[dict(product=product, quantity="0.5", unit_price="1")])
    with pytest.raises(ValidationError):
        create_order(**args, **payload)
    payload["lines"][0]["quantity"] = "2"
    order = create_order(**args, **payload)
    for action in ["submit", "approve"]:
        transition_order(**args, order_id=order.pk, action=action)
    with pytest.raises(ValidationError):
        receive_goods(
            **args,
            order_id=order.pk,
            warehouse=source,
            idempotency_key=uuid.uuid4(),
            lines=[dict(order_line=order.lines.get().pk, quantity="0.5")],
        )
    assert StockBalance.objects.get().on_hand == 10
    args["actor"].is_active = False
    with pytest.raises(PermissionDenied):
        create_order(**args, **payload)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("operation", ["adjust", "transfer", "reserve"])
def test_concurrent_inventory_retry_posts_once(stock, operation):
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL row locks required")
    args, product, source, target = stock
    key = uuid.uuid4()
    if operation == "adjust":
        fn = post_stock_adjustment
        payload = dict(
            warehouse=source,
            reason="Count",
            idempotency_key=key,
            lines=[dict(product=product, quantity_signed="2")],
        )
    elif operation == "transfer":
        fn = transfer_stock
        payload = dict(
            source_warehouse=source,
            destination_warehouse=target,
            idempotency_key=key,
            lines=[dict(product=product, quantity="2")],
        )
    else:
        fn = reserve_stock
        payload = dict(
            product=product,
            warehouse=source,
            quantity="2",
            source_type="MANUAL",
            source_id=uuid.uuid4(),
            idempotency_key=key,
        )

    def run(_):
        close_old_connections()
        try:
            return fn(**args, **payload)[0].pk
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, range(2)))
    assert results[0] == results[1]
    balance = StockBalance.objects.get(warehouse=source)
    assert (balance.on_hand, balance.reserved) == {
        "adjust": (12, 0),
        "transfer": (8, 0),
        "reserve": (10, 2),
    }[operation]
    assert StockReservation.objects.count() == (1 if operation == "reserve" else 0)
