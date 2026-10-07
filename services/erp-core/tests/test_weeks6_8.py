"""Tests assert business outcomes, rollback and tenant boundaries, not implementation text."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError as ModelValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import close_old_connections, connection
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.audit.models import AuditEvent
from apps.billing.models import Invoice, Payment, PaymentAllocation
from apps.billing.services import allocate_payment, change_status, create_invoice
from apps.catalog.models import Product, UnitOfMeasure
from apps.common.commands import Conflict
from apps.finance.selectors import summary
from apps.finance.services import create_expense, void_expense
from apps.intelligence.client import AIUnavailable
from apps.intelligence.models import OCRDocument, RecommendationRun
from apps.intelligence.services import (
    approve_document,
    decide,
    extract,
    run_forecast,
    upload_document,
)
from apps.inventory.models import StockBalance, Warehouse
from apps.partners.models import BusinessPartner
from apps.tenancy.models import Membership


@pytest.fixture
def finance(organization_a, admin_user, admin_membership):
    partner = BusinessPartner.objects.create(
        organization=organization_a, code="F", name="Finance partner", partner_type="BOTH"
    )
    unit = UnitOfMeasure.objects.create(organization=organization_a, name="Each", symbol="f")
    product = Product.objects.create(
        organization=organization_a, sku="F", name="Finance product", unit=unit, purchase_price=4
    )
    warehouse = Warehouse.objects.create(
        organization=organization_a, code="F", name="Finance depot"
    )
    return dict(organization=organization_a, actor=admin_user), partner, product, warehouse


def draft(finance, **overrides):
    args, partner, product, _ = finance
    data = dict(
        idempotency_key=uuid.uuid4(),
        kind="CUSTOMER",
        partner_id=partner.pk,
        reference=str(uuid.uuid4()),
        currency="DZD",
        issued_on=date(2026, 1, 1),
        due_on=date(2026, 2, 1),
        lines=[
            dict(
                product_id=product.pk,
                description="Mouse",
                quantity="2",
                unit_price="10",
                unit_cost="4",
                tax_rate="19",
            )
        ],
    )
    data.update(overrides)
    return create_invoice(**args, **data)


def payment(args, invoice, amount="10", **overrides):
    data = dict(
        idempotency_key=uuid.uuid4(),
        paid_on=date(2026, 1, 15),
        reference="Transfer",
        allocations=[dict(invoice_id=invoice.pk, amount=amount)],
    )
    data.update(overrides)
    return allocate_payment(**args, **data)


def test_invoice_rounding_posting_and_allocation(finance):
    args, _, _, _ = finance
    invoice, _ = draft(finance)
    assert (invoice.subtotal, invoice.tax_total, invoice.total) == (
        Decimal("20"),
        Decimal("3.80"),
        Decimal("23.80"),
    )
    with pytest.raises(Conflict):
        payment(args, invoice)
    change_status(**args, invoice_id=invoice.pk, target="POSTED")
    key = uuid.uuid4()
    first, created = payment(args, invoice, idempotency_key=key)
    retry, created_again = payment(args, invoice, idempotency_key=key)
    assert created and not created_again and retry.pk == first.pk
    invoice.refresh_from_db()
    assert invoice.paid == Decimal("10")
    with pytest.raises(Conflict):
        payment(args, invoice, "11", idempotency_key=key)
    with pytest.raises(Conflict):
        payment(args, invoice, "14")
    assert Payment.objects.count() == PaymentAllocation.objects.count() == 1
    assert summary(args["organization"], "DZD")["receivables"] == "13.80"
    assert summary(args["organization"], "DZD")["gross_margin"] == "12.00"


def test_invoice_draft_retry_and_duplicate_reference(finance):
    key, reference = uuid.uuid4(), "INV-1"
    first, _ = draft(finance, idempotency_key=key, reference=reference)
    retry, created = draft(finance, idempotency_key=key, reference=reference)
    assert first.pk == retry.pk and not created
    with pytest.raises(Conflict):
        draft(finance, reference=reference)
    with pytest.raises(Conflict):
        draft(finance, idempotency_key=key, reference="DIFFERENT")


def test_multi_invoice_allocation_is_atomic(finance):
    args = finance[0]
    a, _ = draft(finance)
    b, _ = draft(finance)
    for invoice in (a, b):
        change_status(**args, invoice_id=invoice.pk, target="POSTED")
    with pytest.raises(Conflict):
        payment(
            args,
            a,
            allocations=[dict(invoice_id=a.pk, amount="5"), dict(invoice_id=b.pk, amount="100")],
        )
    assert not Payment.objects.exists()
    a.refresh_from_db()
    assert a.paid == 0
    payment(
        args, a, allocations=[dict(invoice_id=a.pk, amount="5"), dict(invoice_id=b.pk, amount="7")]
    )
    assert Payment.objects.get().amount == 12


def test_currency_separation_and_void_rules(finance):
    args = finance[0]
    a, _ = draft(finance)
    b, _ = draft(finance, currency="EUR")
    for invoice in (a, b):
        change_status(**args, invoice_id=invoice.pk, target="POSTED")
    with pytest.raises(Conflict):
        payment(
            args,
            a,
            allocations=[dict(invoice_id=a.pk, amount="1"), dict(invoice_id=b.pk, amount="1")],
        )
    payment(args, a)
    with pytest.raises(Conflict):
        change_status(**args, invoice_id=a.pk, target="VOID", reason="Correction")
    change_status(**args, invoice_id=b.pk, target="VOID", reason="Duplicate")
    assert summary(args["organization"], "EUR")["revenue"] == "0.00"
    with pytest.raises(Conflict):
        change_status(**args, invoice_id=b.pk, target="POSTED")


@pytest.mark.parametrize("value", ["0", "-1", "NaN", "Infinity", "0.00001"])
def test_invalid_invoice_quantities(finance, value):
    with pytest.raises(ValidationError):
        draft(finance, lines=[dict(description="Bad", quantity=value, unit_price="10")])
    assert not Invoice.objects.exists()


def test_foreign_partner_and_product_rejected(finance, organization_b):
    partner = BusinessPartner.objects.create(
        organization=organization_b, name="Foreign", code="F", partner_type="BOTH"
    )
    with pytest.raises(ValidationError):
        draft(finance, partner_id=partner.pk)
    with pytest.raises(ValidationError):
        draft(
            finance,
            lines=[
                dict(product_id=uuid.uuid4(), description="Foreign", quantity="1", unit_price="2")
            ],
        )
    assert not Invoice.objects.exists()


def test_expense_summary_void_and_audit_immutability(finance):
    args = finance[0]
    payload = dict(
        idempotency_key=uuid.uuid4(),
        description="Fuel",
        category="Travel",
        amount="4.50",
        currency="DZD",
        spent_on=date(2026, 1, 1),
    )
    expense, _ = create_expense(**args, **payload)
    retry, created = create_expense(**args, **payload)
    assert retry.pk == expense.pk and not created
    assert summary(args["organization"], "DZD")["net_cash_flow"] == "-4.50"
    void_expense(**args, expense_id=expense.pk, reason="Duplicate")
    assert summary(args["organization"], "DZD")["expenses"] == "0.00"
    event = AuditEvent.objects.first()
    with pytest.raises(ModelValidationError):
        event.save()
    with pytest.raises(ModelValidationError):
        AuditEvent.objects.all().update(action="tampered")
    with pytest.raises(ModelValidationError):
        AuditEvent.objects.all().delete()


def test_payment_rolls_back_if_audit_fails(finance):
    args = finance[0]
    invoice, _ = draft(finance)
    change_status(**args, invoice_id=invoice.pk, target="POSTED")
    with (
        patch("apps.billing.services.record", side_effect=RuntimeError("audit failed")),
        pytest.raises(RuntimeError),
    ):
        payment(args, invoice)
    invoice.refresh_from_db()
    assert invoice.paid == 0 and not Payment.objects.exists()


def test_finance_api_tenant_and_roles(
    finance, api_client, organization_b, viewer_user, viewer_membership
):
    args = finance[0]
    invoice, _ = draft(finance)
    headers = {"HTTP_X_ORGANIZATION_ID": str(args["organization"].pk)}
    api_client.force_authenticate(viewer_user)
    assert api_client.get("/api/v1/billing/invoices/", **headers).status_code == 200
    assert (
        api_client.post(f"/api/v1/billing/invoices/{invoice.pk}/post/", {}, **headers).status_code
        == 403
    )
    api_client.force_authenticate(args["actor"])
    Membership.objects.create(organization=organization_b, user=args["actor"], role="ADMINISTRATOR")
    foreign = {"HTTP_X_ORGANIZATION_ID": str(organization_b.pk)}
    assert api_client.get(f"/api/v1/billing/invoices/{invoice.pk}/", **foreign).status_code == 404
    assert api_client.get("/api/v1/audit/events/", **foreign).data["count"] == 0
    assert api_client.get("/api/v1/finance/summary/?currency=XXX", **headers).status_code == 400


@pytest.fixture
def document(finance, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    # The fake image is used only to test orchestration; real OCR is tested in ai-service.
    file = SimpleUploadedFile("invoice.png", b"\x89PNG\r\n\x1a\nfixture", content_type="image/png")
    return upload_document(**finance[0], file=file)


def extracted(document, finance):
    with patch(
        "apps.intelligence.services.call_ai",
        return_value={"model_version": "test-v1", "raw_text": "Invoice", "fields": {}},
    ):
        return extract(**finance[0], document_id=document.pk)


def corrected(finance):
    return dict(
        partner_id=finance[1].pk,
        reference="OCR-1",
        currency="DZD",
        issued_on=date(2026, 1, 1),
        due_on=date(2026, 2, 1),
        lines=[
            dict(description="Reviewed invoice line", quantity="1", unit_price="10", tax_rate="19")
        ],
    )


def test_ocr_human_approval_creates_only_one_draft(finance, document):
    args = finance[0]
    with pytest.raises(Conflict):
        approve_document(**args, document_id=document.pk, corrected=corrected(finance))
    extracted(document, finance)
    result = approve_document(**args, document_id=document.pk, corrected=corrected(finance))
    retry = approve_document(**args, document_id=document.pk, corrected=corrected(finance))
    assert result.invoice_id == retry.invoice_id
    assert result.invoice.status == "DRAFT" and result.invoice.kind == "SUPPLIER"
    assert result.invoice.total == Decimal("11.90")
    assert not StockBalance.objects.exists()
    with pytest.raises(Conflict):
        approve_document(
            **args,
            document_id=document.pk,
            corrected={**corrected(finance), "reference": "different"},
        )


def test_ocr_failure_is_retryable(finance, document):
    with (
        patch("apps.intelligence.services.call_ai", side_effect=AIUnavailable),
        pytest.raises(AIUnavailable),
    ):
        extract(**finance[0], document_id=document.pk)
    document.refresh_from_db()
    assert document.status == "FAILED"
    assert extracted(document, finance).status == "REVIEW"


def test_ocr_private_download_and_approval_permissions(
    finance, document, api_client, organization_b
):
    args = finance[0]
    api_client.force_authenticate(args["actor"])
    Membership.objects.create(organization=organization_b, user=args["actor"], role="MANAGER")
    path = f"/api/v1/intelligence/documents/{document.pk}/download/"
    assert api_client.get(path, HTTP_X_ORGANIZATION_ID=str(organization_b.pk)).status_code == 404
    response = api_client.get(path, HTTP_X_ORGANIZATION_ID=str(args["organization"].pk))
    assert response.status_code == 200 and response["Cache-Control"] == "no-store"
    response.close()
    extracted(document, finance)
    Membership.objects.filter(organization=args["organization"], user=args["actor"]).update(
        role="PURCHASING_AGENT"
    )
    with pytest.raises(PermissionDenied):
        approve_document(**args, document_id=document.pk, corrected=corrected(finance))


def test_ocr_rejects_non_documents(finance):
    with pytest.raises(ValidationError):
        upload_document(**finance[0], file=SimpleUploadedFile("evil.png", b"<html>bad</html>"))
    assert not OCRDocument.objects.exists()


def test_forecast_snapshot_and_decision_do_not_change_stock(finance):
    args, _, product, warehouse = finance
    StockBalance.objects.create(
        organization=args["organization"],
        product=product,
        warehouse=warehouse,
        on_hand=20,
        reserved=5,
    )
    with patch(
        "apps.intelligence.services.call_ai",
        return_value={"model_version": "test-v1", "reorder_quantity": 3, "mae": 1},
    ) as ai:
        run = run_forecast(
            **args,
            product_id=product.pk,
            warehouse_id=warehouse.pk,
            lead_time_days=7,
            horizon_days=30,
        )
    assert run.inputs["available"] == 15
    assert (
        len(run.inputs["daily_demand"]) == 90
        and ai.call_args.kwargs["data"]["daily_demand"] == [0] * 90
    )
    decide(**args, run_id=run.pk, decision="ACCEPTED", note="Reviewed stock")
    decide(**args, run_id=run.pk, decision="ACCEPTED", note="Reviewed stock")
    with pytest.raises(Conflict):
        decide(**args, run_id=run.pk, decision="REJECTED", note="Change history")
    assert StockBalance.objects.get().on_hand == 20
    assert not Invoice.objects.exists()


def test_forecast_failure_and_foreign_input(finance, organization_b):
    args, _, product, warehouse = finance
    with (
        patch("apps.intelligence.services.call_ai", side_effect=AIUnavailable),
        pytest.raises(AIUnavailable),
    ):
        run_forecast(
            **args,
            product_id=product.pk,
            warehouse_id=warehouse.pk,
            lead_time_days=7,
            horizon_days=30,
        )
    assert RecommendationRun.objects.get().status == "FAILED"
    with pytest.raises(ValidationError):
        run_forecast(
            **args,
            product_id=uuid.uuid4(),
            warehouse_id=warehouse.pk,
            lead_time_days=7,
            horizon_days=30,
        )


def test_inactive_membership_cannot_write(finance):
    args = finance[0]
    Membership.objects.filter(user=args["actor"], organization=args["organization"]).update(
        is_active=False
    )
    with pytest.raises(PermissionDenied):
        draft(finance)


def test_finance_write_api_and_expense_void(finance, api_client):
    args, partner, _, _ = finance
    api_client.force_authenticate(args["actor"])
    headers = {"HTTP_X_ORGANIZATION_ID": str(args["organization"].pk)}
    response = api_client.post(
        "/api/v1/billing/invoices/",
        dict(
            idempotency_key=str(uuid.uuid4()),
            kind="SUPPLIER",
            partner_id=str(partner.pk),
            reference="API-001",
            currency="EUR",
            issued_on="2026-01-01",
            due_on="2026-02-01",
            lines=[dict(description="Services", quantity="1", unit_price="5", tax_rate="0")],
        ),
        format="json",
        **headers,
    )
    assert response.status_code == 201, response.data
    invoice_id = response.data["id"]
    assert (
        api_client.post(
            f"/api/v1/billing/invoices/{invoice_id}/post/", {}, format="json", **headers
        ).status_code
        == 200
    )
    assert (
        api_client.post(
            f"/api/v1/billing/invoices/{invoice_id}/void/",
            {"reason": "Duplicate"},
            format="json",
            **headers,
        ).status_code
        == 200
    )
    response = api_client.post(
        "/api/v1/finance/expenses/",
        dict(
            idempotency_key=str(uuid.uuid4()),
            description="Fuel",
            category="Travel",
            amount="5",
            currency="DZD",
            spent_on="2026-01-01",
        ),
        format="json",
        **headers,
    )
    assert response.status_code == 201, response.data
    assert (
        api_client.post(
            f"/api/v1/finance/expenses/{response.data['id']}/void/",
            {"reason": "Duplicate"},
            format="json",
            **headers,
        ).status_code
        == 200
    )


def test_source_order_invoice_snapshots_and_blocks_duplicate(finance):
    from apps.inventory.services import post_stock_adjustment
    from apps.sales.services import confirm_order, save_draft

    args, partner, product, warehouse = finance
    post_stock_adjustment(
        **args,
        warehouse=warehouse,
        reason="Opening",
        idempotency_key=uuid.uuid4(),
        lines=[dict(product=product, quantity_signed="20", unit_cost="4")],
    )
    order = save_draft(
        **args,
        customer=partner,
        warehouse=warehouse,
        lines=[dict(product=product, quantity="2", unit_price="10")],
    )
    confirm_order(**args, order_id=order.pk)
    invoice, _ = draft(finance, sales_order_id=order.pk, lines=[])
    assert invoice.sales_order_id == order.pk and invoice.cost_total == 8
    assert invoice.lines.get().quantity == 2
    with pytest.raises(Conflict):
        draft(finance, sales_order_id=order.pk, lines=[])


@pytest.mark.django_db(transaction=True)
def test_concurrent_payment_retries_post_once(finance):
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL row locks required")
    args = finance[0]
    invoice, _ = draft(finance)
    change_status(**args, invoice_id=invoice.pk, target="POSTED")
    key = uuid.uuid4()

    def run(_):
        close_old_connections()
        try:
            return payment(args, invoice, idempotency_key=key)[0].pk
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(run, range(2)))
    assert result[0] == result[1] and Payment.objects.count() == 1
    invoice.refresh_from_db()
    assert invoice.paid == 10
