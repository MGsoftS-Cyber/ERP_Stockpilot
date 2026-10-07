# Teaching edition: Build read queries within the selected organization.
from apps.inventory.models import (
    StockAdjustment,
    StockBalance,
    StockMovement,
    StockReservation,
    StockTransfer,
    Warehouse,
)


def warehouses_for_organization(organization):
    return Warehouse.objects.for_organization(organization)


def movements_for_organization(organization):
    return StockMovement.objects.for_organization(organization).select_related(
        "product",
        "warehouse",
        "created_by",
    )


def balances_for_organization(organization):
    return StockBalance.objects.for_organization(organization).select_related(
        "product",
        "warehouse",
    )


def adjustments_for_organization(organization):
    return StockAdjustment.objects.for_organization(organization).prefetch_related("lines__product")


def transfers_for_organization(organization):
    return StockTransfer.objects.for_organization(organization).prefetch_related("lines__product")


def reservations_for_organization(organization):
    return StockReservation.objects.for_organization(organization).select_related(
        "product",
        "warehouse",
    )
