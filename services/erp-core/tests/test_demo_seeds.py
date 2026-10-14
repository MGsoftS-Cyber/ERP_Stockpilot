import pytest
from django.core.management import call_command

from apps.billing.models import Invoice
from apps.inventory.models import StockMovement
from apps.purchasing.models import PurchaseOrder
from apps.sales.models import SalesOrder


@pytest.mark.django_db
def test_descriptive_seeds_preserve_legacy_demo_drafts_and_invoice_replay():
    call_command("seed_finance_demo")
    counts = (
        PurchaseOrder.objects.count(),
        SalesOrder.objects.count(),
        Invoice.objects.count(),
        StockMovement.objects.count(),
    )
    assert Invoice.objects.get(reference="DEMO-INVOICE-001")
    PurchaseOrder.objects.filter(notes="PURCHASING_DEMO").update(notes="WEEK4_DEMO")
    SalesOrder.objects.filter(notes="SALES_DEMO").update(notes="WEEK5_DEMO")
    call_command("seed_finance_demo")
    assert (
        PurchaseOrder.objects.count(),
        SalesOrder.objects.count(),
        Invoice.objects.count(),
        StockMovement.objects.count(),
    ) == counts
    assert not PurchaseOrder.objects.filter(notes="WEEK4_DEMO").exists()
    assert not SalesOrder.objects.filter(notes="WEEK5_DEMO").exists()
    assert PurchaseOrder.objects.filter(notes="PURCHASING_DEMO").exists()
    assert SalesOrder.objects.filter(notes="SALES_DEMO").exists()
