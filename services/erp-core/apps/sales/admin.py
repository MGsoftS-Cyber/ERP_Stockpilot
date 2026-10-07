from django.contrib import admin

from apps.sales.models import (
    CustomerReturn,
    CustomerReturnLine,
    SalesEvent,
    SalesOrder,
    SalesOrderLine,
    Shipment,
    ShipmentLine,
)


class SalesReadOnlyAdmin(admin.ModelAdmin):
    # Admin is for inspection; editing here would bypass the reservation services.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


for model in (
    SalesOrder,
    SalesOrderLine,
    Shipment,
    ShipmentLine,
    CustomerReturn,
    CustomerReturnLine,
    SalesEvent,
):
    admin.site.register(model, SalesReadOnlyAdmin)
