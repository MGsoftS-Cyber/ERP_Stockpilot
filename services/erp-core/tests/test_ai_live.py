"""Optional live service test; ordinary pytest does not require a running AI server."""

import io
import os
import uuid

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image, ImageDraw, ImageFont

from apps.billing.models import Invoice
from apps.catalog.models import Product, UnitOfMeasure
from apps.inventory.models import Warehouse
from apps.partners.models import BusinessPartner


@pytest.mark.skipif(os.getenv("AI_INTEGRATION") != "1", reason="Requires the live FastAPI service")
def test_live_upload_review_invoice_payment_and_forecast(
    api_client, organization_a, admin_user, admin_membership, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path
    api_client.force_authenticate(admin_user)
    headers = {"HTTP_X_ORGANIZATION_ID": str(organization_a.pk)}
    partner = BusinessPartner.objects.create(
        organization=organization_a, code="LIVE", name="Live Supplier", partner_type="SUPPLIER"
    )
    unit = UnitOfMeasure.objects.create(organization=organization_a, name="Each", symbol="live")
    product = Product.objects.create(
        organization=organization_a, sku="LIVE", name="Live product", unit=unit, minimum_stock=3
    )
    warehouse = Warehouse.objects.create(
        organization=organization_a, code="LIVE", name="Live warehouse"
    )
    image = Image.new("RGB", (1500, 600), "white")
    ImageDraw.Draw(image).multiline_text(
        (50, 50),
        "Invoice: LIVE-123\nDate: 2026-01-15\nTotal: 119.00",
        fill="black",
        font=ImageFont.truetype("DejaVuSans.ttf", 48),
        spacing=20,
    )
    output = io.BytesIO()
    image.save(output, format="PNG")
    response = api_client.post(
        "/api/v1/intelligence/documents/upload/",
        {"file": SimpleUploadedFile("invoice.png", output.getvalue(), content_type="image/png")},
        format="multipart",
        **headers,
    )
    assert response.status_code == 201, response.data
    document_id = response.data["id"]
    response = api_client.post(
        f"/api/v1/intelligence/documents/{document_id}/extract/", {}, format="json", **headers
    )
    assert response.status_code == 200, response.data
    assert response.data["extraction"]["fields"]["reference"]["value"] == "LIVE-123"
    reviewed = dict(
        partner_id=str(partner.pk),
        reference="LIVE-123",
        currency="DZD",
        issued_on="2026-01-15",
        due_on="2026-02-15",
        lines=[
            dict(
                product_id=str(product.pk),
                description="Reviewed",
                quantity="1",
                unit_price="100",
                unit_cost="80",
                tax_rate="19",
            )
        ],
    )
    response = api_client.post(
        f"/api/v1/intelligence/documents/{document_id}/approve/", reviewed, format="json", **headers
    )
    assert response.status_code == 200, response.data
    invoice_id = response.data["invoice"]
    assert Invoice.objects.get(pk=invoice_id).status == "DRAFT"
    response = api_client.post(
        f"/api/v1/billing/invoices/{invoice_id}/post/", {}, format="json", **headers
    )
    assert response.status_code == 200, response.data
    response = api_client.post(
        "/api/v1/billing/payments/",
        dict(
            idempotency_key=str(uuid.uuid4()),
            paid_on="2026-01-16",
            reference="Live transfer",
            allocations=[dict(invoice_id=invoice_id, amount="119")],
        ),
        format="json",
        **headers,
    )
    assert response.status_code == 201, response.data
    response = api_client.get("/api/v1/finance/summary/?currency=DZD", **headers)
    assert response.data["payables"] == "0.00" and response.data["cash_out"] == "119.00"
    response = api_client.post(
        "/api/v1/intelligence/forecasts/",
        dict(
            product_id=str(product.pk),
            warehouse_id=str(warehouse.pk),
            lead_time_days=7,
            horizon_days=30,
        ),
        format="json",
        **headers,
    )
    assert response.status_code == 201, response.data
    assert response.data["result"]["reorder_quantity"] == 3
    run_id = response.data["id"]
    response = api_client.post(
        f"/api/v1/intelligence/forecasts/{run_id}/decide/",
        {"decision": "ACCEPTED", "note": "Checked minimum stock"},
        format="json",
        **headers,
    )
    assert response.status_code == 200, response.data
