# Teaching edition: Configure Django admin separately from the React interface.
from django.contrib import admin

from apps.inventory.models import (
    StockAdjustment,
    StockAdjustmentLine,
    StockBalance,
    StockMovement,
    StockReservation,
    StockTransfer,
    StockTransferLine,
    Warehouse,
)

admin.site.register(Warehouse)


class ReadOnlyInventoryAdmin(admin.ModelAdmin):
    """Keep posted inventory records visible but mutable only through services."""

    def has_view_permission(self, request, obj=None) -> bool:
        return request.user.is_superuser

    # Control whether admin may create a record without a service.
    def has_add_permission(self, request) -> bool:
        return False

    # Control whether an admin edit could bypass business rules.
    def has_change_permission(self, request, obj=None) -> bool:
        return False

    # Protect posted records from destructive admin deletion.
    def has_delete_permission(self, request, obj=None) -> bool:
        return False


admin.site.register(
    [
        StockAdjustment,
        StockAdjustmentLine,
        StockTransfer,
        StockTransferLine,
        StockReservation,
    ],
    ReadOnlyInventoryAdmin,
)


@admin.register(StockMovement)
class StockMovementAdmin(ReadOnlyInventoryAdmin):
    list_display = (
        "occurred_at",
        "organization",
        "product",
        "warehouse",
        "movement_type",
        "quantity_signed",
    )
    list_filter = ("organization", "warehouse", "movement_type")
    search_fields = ("product__sku", "product__name")


@admin.register(StockBalance)
class StockBalanceAdmin(ReadOnlyInventoryAdmin):
    list_display = (
        "organization",
        "product",
        "warehouse",
        "on_hand",
        "reserved",
        "available",
    )
    list_filter = ("organization", "warehouse")
    search_fields = ("product__sku", "product__name")
