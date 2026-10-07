# Teaching edition: Verify business behavior using isolated test data.
from decimal import Decimal

import pytest

from apps.catalog.models import Category, Product, TaxRate, UnitOfMeasure
from apps.tenancy.models import Membership


@pytest.mark.django_db
def test_category_list_is_filtered_by_selected_organization(
    api_client,
    admin_user,
    organization_a,
    organization_b,
    admin_membership,
):
    Category.objects.create(organization=organization_a, code="A", name="Category A")
    Category.objects.create(organization=organization_b, code="B", name="Category B")
    api_client.force_authenticate(admin_user)

    response = api_client.get(
        "/api/v1/catalog/categories/",
        HTTP_X_ORGANIZATION_ID=str(organization_a.id),
    )

    assert response.status_code == 200
    assert [item["code"] for item in response.data["results"]] == ["A"]


@pytest.mark.django_db
def test_user_cannot_select_an_organization_without_membership(
    api_client,
    admin_user,
    organization_b,
    admin_membership,
):
    api_client.force_authenticate(admin_user)

    response = api_client.get(
        "/api/v1/catalog/categories/",
        HTTP_X_ORGANIZATION_ID=str(organization_b.id),
    )

    assert response.status_code == 403
    assert response.data["error"]["status"] == 403


@pytest.mark.django_db
def test_organization_header_is_mandatory(api_client, admin_user, admin_membership):
    api_client.force_authenticate(admin_user)

    response = api_client.get("/api/v1/catalog/categories/")

    assert response.status_code == 400
    assert "X-Organization-ID" in response.data["error"]["detail"]


@pytest.mark.django_db
def test_viewer_can_read_but_cannot_create(
    api_client,
    viewer_user,
    viewer_membership,
    organization_a,
):
    Category.objects.create(organization=organization_a, code="READ", name="Readable")
    api_client.force_authenticate(viewer_user)
    headers = {"HTTP_X_ORGANIZATION_ID": str(organization_a.id)}

    read_response = api_client.get("/api/v1/catalog/categories/", **headers)
    create_response = api_client.post(
        "/api/v1/catalog/categories/",
        {"code": "NO", "name": "Not allowed"},
        format="json",
        **headers,
    )

    assert read_response.status_code == 200
    assert create_response.status_code == 403


@pytest.mark.django_db
def test_product_rejects_related_data_from_another_organization(
    api_client,
    admin_user,
    organization_a,
    organization_b,
    admin_membership,
):
    unit = UnitOfMeasure.objects.create(
        organization=organization_a,
        name="Pieces",
        symbol="pcs",
    )
    foreign_category = Category.objects.create(
        organization=organization_b,
        code="FOREIGN",
        name="Foreign category",
    )
    api_client.force_authenticate(admin_user)

    response = api_client.post(
        "/api/v1/catalog/products/",
        {
            "sku": "P-001",
            "name": "Protected product",
            "unit": str(unit.id),
            "category": str(foreign_category.id),
            "purchase_price": "10.0000",
            "selling_price": "15.0000",
            "minimum_stock": "1.0000",
        },
        format="json",
        HTTP_X_ORGANIZATION_ID=str(organization_a.id),
    )

    assert response.status_code == 400
    assert "category" in response.data["error"]["detail"]
    assert Product.objects.count() == 0


@pytest.mark.django_db
def test_admin_creates_product_in_selected_organization(
    api_client,
    admin_user,
    organization_a,
    admin_membership,
):
    unit = UnitOfMeasure.objects.create(
        organization=organization_a,
        name="Pieces",
        symbol="pcs",
    )
    category = Category.objects.create(
        organization=organization_a,
        code="ELEC",
        name="Electronics",
    )
    tax = TaxRate.objects.create(
        organization=organization_a,
        name="VAT 19",
        rate=Decimal("19.00"),
    )
    api_client.force_authenticate(admin_user)

    response = api_client.post(
        "/api/v1/catalog/products/",
        {
            "sku": "MOUSE-001",
            "name": "Wireless Mouse",
            "unit": str(unit.id),
            "category": str(category.id),
            "tax_rate": str(tax.id),
            "purchase_price": "20.0000",
            "selling_price": "35.0000",
            "minimum_stock": "5.0000",
        },
        format="json",
        HTTP_X_ORGANIZATION_ID=str(organization_a.id),
    )

    assert response.status_code == 201
    product = Product.objects.get(sku="MOUSE-001")
    assert product.organization == organization_a
    assert product.created_by == admin_user


@pytest.mark.django_db
def test_stock_operator_can_create_warehouse(api_client, organization_a, db):
    from apps.inventory.models import Warehouse
    from apps.tenancy.models import User

    stock_user = User.objects.create_user(email="stock@example.com", password="StrongPass123!")
    Membership.objects.create(
        user=stock_user,
        organization=organization_a,
        role=Membership.Role.STOCK_OPERATOR,
    )
    api_client.force_authenticate(stock_user)

    response = api_client.post(
        "/api/v1/inventory/warehouses/",
        {"code": "MAIN", "name": "Main Warehouse", "address": "Algiers"},
        format="json",
        HTTP_X_ORGANIZATION_ID=str(organization_a.id),
    )

    assert response.status_code == 201
    assert Warehouse.objects.get(code="MAIN").organization == organization_a
