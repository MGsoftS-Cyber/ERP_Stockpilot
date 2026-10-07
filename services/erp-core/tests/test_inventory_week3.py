# Teaching edition: Verify business behavior using isolated test data.
import uuid
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError as DjangoValidationError

from apps.catalog.models import Product, UnitOfMeasure
from apps.inventory.models import (
    StockAdjustment,
    StockBalance,
    StockMovement,
    StockReservation,
    Warehouse,
)
from apps.inventory.services import (
    InsufficientStock,
    post_stock_adjustment,
    reconciliation_report,
    release_reservation,
    reserve_stock,
    transfer_stock,
)


@pytest.fixture
def unit(organization_a):
    return UnitOfMeasure.objects.create(
        organization=organization_a,
        name="Pieces",
        symbol="pcs",
        allows_decimals=False,
    )


@pytest.fixture
def product(organization_a, unit):
    return Product.objects.create(
        organization=organization_a,
        sku="W3-001",
        name="Week 3 product",
        unit=unit,
        purchase_price=Decimal("8.5000"),
        minimum_stock=Decimal("5.0000"),
    )


@pytest.fixture
def main_warehouse(organization_a):
    return Warehouse.objects.create(
        organization=organization_a,
        code="MAIN",
        name="Main Warehouse",
    )


@pytest.fixture
def overflow_warehouse(organization_a):
    return Warehouse.objects.create(
        organization=organization_a,
        code="OVERFLOW",
        name="Overflow Warehouse",
    )


def post_opening(*, organization, actor, product, warehouse, quantity="10.0000"):
    return post_stock_adjustment(
        organization=organization,
        actor=actor,
        warehouse=warehouse,
        reason="Opening count",
        idempotency_key=uuid.uuid4(),
        lines=[
            {
                "product": product,
                "quantity_signed": Decimal(quantity),
                "unit_cost": product.purchase_price,
            }
        ],
    )


@pytest.mark.django_db
def test_adjustment_posts_immutable_movement_and_balance(
    organization_a,
    admin_user,
    product,
    main_warehouse,
):
    adjustment, created = post_opening(
        organization=organization_a,
        actor=admin_user,
        product=product,
        warehouse=main_warehouse,
    )

    movement = StockMovement.objects.get(source_id=adjustment.id)
    balance = StockBalance.objects.get(product=product, warehouse=main_warehouse)
    assert created is True
    assert movement.movement_type == StockMovement.MovementType.ADJUSTMENT_IN
    assert movement.quantity_signed == Decimal("10.0000")
    assert balance.on_hand == Decimal("10.0000")
    assert balance.reserved == Decimal("0.0000")
    assert balance.available == Decimal("10.0000")

    movement.quantity_signed = Decimal("99.0000")
    with pytest.raises(DjangoValidationError):
        movement.save()
    with pytest.raises(DjangoValidationError):
        movement.delete()


@pytest.mark.django_db
def test_adjustment_idempotency_does_not_duplicate_stock(
    organization_a,
    admin_user,
    product,
    main_warehouse,
):
    idempotency_key = uuid.uuid4()
    command = {
        "organization": organization_a,
        "actor": admin_user,
        "warehouse": main_warehouse,
        "reason": "Count correction",
        "idempotency_key": idempotency_key,
        "lines": [{"product": product, "quantity_signed": Decimal("3.0000")}],
    }

    first, first_created = post_stock_adjustment(**command)
    second, second_created = post_stock_adjustment(**command)

    assert first.id == second.id
    assert first_created is True
    assert second_created is False
    assert StockAdjustment.objects.count() == 1
    assert StockMovement.objects.count() == 1
    assert StockBalance.objects.get().on_hand == Decimal("3.0000")


@pytest.mark.django_db
def test_negative_adjustment_rolls_back_when_stock_is_insufficient(
    organization_a,
    admin_user,
    product,
    main_warehouse,
):
    with pytest.raises(InsufficientStock):
        post_stock_adjustment(
            organization=organization_a,
            actor=admin_user,
            warehouse=main_warehouse,
            reason="Invalid negative count",
            idempotency_key=uuid.uuid4(),
            lines=[{"product": product, "quantity_signed": Decimal("-1.0000")}],
        )

    assert StockAdjustment.objects.count() == 0
    assert StockMovement.objects.count() == 0
    assert StockBalance.objects.count() == 0


@pytest.mark.django_db
def test_transfer_posts_paired_movements_atomically(
    organization_a,
    admin_user,
    product,
    main_warehouse,
    overflow_warehouse,
):
    post_opening(
        organization=organization_a,
        actor=admin_user,
        product=product,
        warehouse=main_warehouse,
    )

    transfer, created = transfer_stock(
        organization=organization_a,
        actor=admin_user,
        source_warehouse=main_warehouse,
        destination_warehouse=overflow_warehouse,
        reason="Rebalance storage",
        idempotency_key=uuid.uuid4(),
        lines=[
            {
                "product": product,
                "quantity": Decimal("4.0000"),
                "unit_cost": Decimal("8.5000"),
            }
        ],
    )

    transfer_movements = StockMovement.objects.filter(source_id=transfer.id)
    source_balance = StockBalance.objects.get(
        product=product,
        warehouse=main_warehouse,
    )
    destination_balance = StockBalance.objects.get(
        product=product,
        warehouse=overflow_warehouse,
    )
    assert created is True
    assert set(transfer_movements.values_list("movement_type", flat=True)) == {
        StockMovement.MovementType.TRANSFER_OUT,
        StockMovement.MovementType.TRANSFER_IN,
    }
    assert sum(
        transfer_movements.values_list("quantity_signed", flat=True),
        Decimal("0"),
    ) == Decimal("0")
    assert source_balance.on_hand == Decimal("6.0000")
    assert destination_balance.on_hand == Decimal("4.0000")


@pytest.mark.django_db
def test_reservation_changes_available_stock_and_release_is_idempotent(
    organization_a,
    admin_user,
    product,
    main_warehouse,
):
    post_opening(
        organization=organization_a,
        actor=admin_user,
        product=product,
        warehouse=main_warehouse,
    )
    reservation, created = reserve_stock(
        organization=organization_a,
        actor=admin_user,
        product=product,
        warehouse=main_warehouse,
        quantity=Decimal("3.0000"),
        source_type=StockReservation.SourceType.MANUAL,
        source_id=uuid.uuid4(),
        idempotency_key=uuid.uuid4(),
    )

    balance = StockBalance.objects.get(product=product, warehouse=main_warehouse)
    assert created is True
    assert balance.on_hand == Decimal("10.0000")
    assert balance.reserved == Decimal("3.0000")
    assert balance.available == Decimal("7.0000")

    release_reservation(organization=organization_a, reservation_id=reservation.id)
    release_reservation(organization=organization_a, reservation_id=reservation.id)
    balance.refresh_from_db()
    reservation.refresh_from_db()
    assert reservation.status == StockReservation.Status.RELEASED
    assert balance.reserved == Decimal("0.0000")


@pytest.mark.django_db
def test_reservation_rejects_quantity_above_available(
    organization_a,
    admin_user,
    product,
    main_warehouse,
):
    post_opening(
        organization=organization_a,
        actor=admin_user,
        product=product,
        warehouse=main_warehouse,
        quantity="2.0000",
    )
    balance = StockBalance.objects.get(product=product, warehouse=main_warehouse)
    assert balance.is_low_stock is True
    with pytest.raises(InsufficientStock):
        reserve_stock(
            organization=organization_a,
            actor=admin_user,
            product=product,
            warehouse=main_warehouse,
            quantity=Decimal("3.0000"),
            source_type=StockReservation.SourceType.MANUAL,
            source_id=uuid.uuid4(),
            idempotency_key=uuid.uuid4(),
        )


@pytest.mark.django_db
def test_ledger_reconciles_with_balance_projection(
    organization_a,
    admin_user,
    product,
    main_warehouse,
):
    post_opening(
        organization=organization_a,
        actor=admin_user,
        product=product,
        warehouse=main_warehouse,
    )

    report = reconciliation_report(organization=organization_a)

    assert len(report) == 1
    assert report[0].ledger_total == Decimal("10.0000")
    assert report[0].balance_on_hand == Decimal("10.0000")
    assert report[0].is_reconciled is True


@pytest.mark.django_db
def test_adjustment_api_rejects_product_from_another_organization(
    api_client,
    admin_user,
    admin_membership,
    organization_a,
    organization_b,
    main_warehouse,
):
    foreign_unit = UnitOfMeasure.objects.create(
        organization=organization_b,
        name="Foreign pieces",
        symbol="foreign-pcs",
    )
    foreign_product = Product.objects.create(
        organization=organization_b,
        sku="FOREIGN",
        name="Foreign product",
        unit=foreign_unit,
    )
    api_client.force_authenticate(admin_user)

    response = api_client.post(
        "/api/v1/inventory/stock-adjustments/",
        {
            "warehouse": str(main_warehouse.id),
            "reason": "Must be rejected",
            "idempotency_key": str(uuid.uuid4()),
            "lines": [
                {
                    "product": str(foreign_product.id),
                    "quantity_signed": "1.0000",
                    "unit_cost": "0.0000",
                }
            ],
        },
        format="json",
        HTTP_X_ORGANIZATION_ID=str(organization_a.id),
    )

    assert response.status_code == 400
    assert StockMovement.objects.count() == 0


@pytest.mark.django_db
def test_viewer_cannot_post_inventory_adjustment(
    api_client,
    viewer_user,
    viewer_membership,
    organization_a,
    product,
    main_warehouse,
):
    api_client.force_authenticate(viewer_user)

    response = api_client.post(
        "/api/v1/inventory/stock-adjustments/",
        {
            "warehouse": str(main_warehouse.id),
            "reason": "Viewer must not post",
            "idempotency_key": str(uuid.uuid4()),
            "lines": [
                {
                    "product": str(product.id),
                    "quantity_signed": "1.0000",
                    "unit_cost": "0.0000",
                }
            ],
        },
        format="json",
        HTTP_X_ORGANIZATION_ID=str(organization_a.id),
    )

    assert response.status_code == 403
    assert StockMovement.objects.count() == 0
