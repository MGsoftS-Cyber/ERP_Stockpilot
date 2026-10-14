import pytest
from rest_framework.exceptions import ValidationError

from apps.extensions import registry
from apps.extensions.models import MarketplaceRelease
from apps.finance.selectors import summary


def test_summary_keeps_currency_contract_in_three_queries(
    organization_a, django_assert_num_queries
):
    with django_assert_num_queries(3):
        result = summary(organization_a, "EUR")
    assert result["currency"] == "EUR"
    assert all(value == "0.00" for key, value in result.items() if key != "currency")


def test_cached_bundled_manifest_cannot_be_mutated_by_caller():
    first = registry.bundled_releases()
    first[0]["manifest"]["settings"]["threshold"] = 999
    second = registry.bundled_releases()
    assert second[0]["manifest"]["settings"]["threshold"] == 5


def test_resolve_validates_only_requested_approved_release(
    organization_a, django_assert_num_queries
):
    manifest = {**registry.bundled_releases()[0]["manifest"], "id": "community-alert"}
    MarketplaceRelease.objects.create(
        organization=organization_a,
        slug=manifest["id"],
        version=manifest["version"],
        manifest=manifest,
        checksum=registry.checksum(manifest),
        summary="Reviewed alert",
        status="approved",
    )
    # An unrelated corrupt row does not turn every installation into a catalog scan.
    MarketplaceRelease.objects.create(
        organization=organization_a,
        slug="unrelated",
        version="1.0.0",
        manifest={},
        checksum="invalid",
        summary="Broken fixture",
        status="approved",
    )
    with django_assert_num_queries(1):
        release = registry.resolve("community-alert", "1.0.0")
    assert release["manifest"] == manifest
    with pytest.raises(ValidationError):
        registry.resolve("unrelated", "1.0.0")
