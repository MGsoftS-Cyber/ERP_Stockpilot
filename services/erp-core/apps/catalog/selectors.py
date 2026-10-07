# Teaching edition: Build read queries within the selected organization.
from apps.catalog.models import Category, Product, TaxRate, UnitOfMeasure


def products_for_organization(organization):
    return Product.objects.for_organization(organization).select_related(
        "category",
        "unit",
        "tax_rate",
    )


def categories_for_organization(organization):
    return Category.objects.for_organization(organization)


def units_for_organization(organization):
    return UnitOfMeasure.objects.for_organization(organization)


def tax_rates_for_organization(organization):
    return TaxRate.objects.for_organization(organization)
