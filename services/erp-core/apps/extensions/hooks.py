"""Explicit read-only hooks. All ORM queries receive an authorized organization."""

from django.db.models import F

from apps.inventory.models import StockBalance


def execute(manifest, config, organization):
    if manifest["hook"] == "dashboard.notice":
        return {"kind": "notice", "message": config["message"]}
    # Hard cap prevents a plugin screen from exporting an unbounded inventory table.
    rows = (
        StockBalance.objects.filter(
            organization=organization,
            on_hand__lte=F("reserved") + config["threshold"],
        )
        .select_related("product", "warehouse")
        .order_by("product__sku", "warehouse__code")[:100]
    )
    return {
        "kind": "low_stock",
        "limit": 100,
        "rows": [
            {
                "sku": row.product.sku,
                "warehouse": row.warehouse.code,
                "available": str(row.on_hand - row.reserved),
            }
            for row in rows
        ],
    }
