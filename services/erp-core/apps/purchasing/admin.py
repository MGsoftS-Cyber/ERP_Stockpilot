# Teaching edition: Configure Django admin separately from the React interface.
from django.contrib import admin

from apps.purchasing.models import (
    GoodsReceipt,
    GoodsReceiptLine,
    PurchaseEvent,
    PurchaseOrder,
    PurchaseOrderLine,
)


class ReadOnlyPurchaseAdmin(admin.ModelAdmin):
    # Control whether admin may create a record without a service.
    def has_add_permission(self, request):
        return False

    # Control whether an admin edit could bypass business rules.
    def has_change_permission(self, request, obj=None):
        return False

    # Protect posted records from destructive admin deletion.
    def has_delete_permission(self, request, obj=None):
        return False


for model in (PurchaseOrder, PurchaseOrderLine, GoodsReceipt, GoodsReceiptLine, PurchaseEvent):
    admin.site.register(model, ReadOnlyPurchaseAdmin)
