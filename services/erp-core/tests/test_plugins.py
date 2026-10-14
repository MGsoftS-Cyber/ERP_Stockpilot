"""Behavioral tests: lifecycle, stale requests, isolation and atomic failure recovery."""

from unittest.mock import patch
from uuid import uuid4

import pytest
from django.core.exceptions import ValidationError as ModelValidationError
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from apps.common.commands import Conflict
from apps.extensions.models import Installation, Revision
from apps.extensions.registry import resolve, validate
from apps.extensions.services import change

pytestmark = pytest.mark.django_db


@pytest.fixture
def operate(admin_user, admin_membership, organization_a):
    def run(operation="install", expected_revision=0, slug="stock-alerts", **options):
        command = (
            dict(
                operation=operation,
                slug=slug,
                expected_revision=expected_revision,
                idempotency_key=uuid4(),
            )
            | options
        )
        return change(organization=organization_a, actor=admin_user, command=command)

    return run


def test_install_configure_update_rollback_retains_history(operate):
    first = operate(version="1.0.0")
    operate("configure", 1, configuration={"threshold": 23})
    third = operate("update", 2, version="1.1.0")
    assert third.snapshot["configuration"] == {"threshold": 23}
    fourth = operate("rollback", 3, target_revision=first.number)
    assert fourth.number == 4 and fourth.snapshot["release"]["version"] == "1.0.0"
    assert fourth.snapshot["configuration"] == {"threshold": 5}
    assert Revision.objects.count() == 4


def test_stale_revision_cannot_overwrite_new_state(operate):
    operate(version="1.0.0")
    with pytest.raises(Conflict):
        operate("disable", 0)
    assert Installation.objects.get().enabled


def test_same_command_replays_without_duplicate_history(operate):
    key = uuid4()
    first = operate(version="1.0.0", idempotency_key=key)
    second = operate(version="1.0.0", idempotency_key=key)
    assert first.pk == second.pk and Revision.objects.count() == 1
    with pytest.raises(Conflict):
        operate(version="1.1.0", idempotency_key=key)


def test_failed_health_check_rolls_back_update_and_audit(operate):
    operate(version="1.0.0")
    with patch("apps.extensions.hooks.execute", side_effect=RuntimeError("unavailable")):
        with pytest.raises(APIException):
            operate("update", 1, version="1.1.0")
    assert Installation.objects.get().release["version"] == "1.0.0"
    assert Revision.objects.count() == 1


def test_dependency_blocks_install_and_disable(operate):
    with pytest.raises(Conflict):
        operate(slug="warehouse-notice", version="1.0.0")
    operate(version="1.0.0")
    operate(slug="warehouse-notice", version="1.0.0")
    with pytest.raises(Conflict):
        operate("disable", 1)
    operate("disable", 1, slug="warehouse-notice")
    operate("disable", 1)
    assert not Installation.objects.filter(enabled=True).exists()


@pytest.mark.parametrize("value", [-1, 1.5, True, "10", 100001])
def test_invalid_configuration_never_changes_state(operate, value):
    operate(version="1.0.0")
    with pytest.raises(ValidationError):
        operate("configure", 1, configuration={"threshold": value})
    assert Installation.objects.get().revision == 1


def test_unknown_releases_and_executable_hooks_rejected():
    with pytest.raises(ValidationError):
        resolve("../../evil", "1.0.0")
    manifest = resolve("stock-alerts", "1.0.0")["manifest"]
    manifest["hook"] = "os.system"
    with pytest.raises(ValidationError):
        validate(manifest)


def test_viewer_cannot_install(viewer_user, viewer_membership, organization_a):
    with pytest.raises(PermissionDenied):
        change(organization=organization_a, actor=viewer_user, command={})


def test_plugin_history_tenant_isolation(operate, api_client, admin_user, organization_b):
    operate(version="1.0.0")
    from apps.tenancy.models import Membership

    Membership.objects.create(user=admin_user, organization=organization_b, role="ADMINISTRATOR")
    api_client.force_authenticate(admin_user)
    response = api_client.get(
        "/api/v1/plugins/stock-alerts/history/", HTTP_X_ORGANIZATION_ID=str(organization_b.id)
    )
    assert response.status_code == 200 and response.data == []


def test_history_is_immutable(operate):
    operate(version="1.0.0")
    with pytest.raises(ModelValidationError):
        Revision.objects.update(snapshot={})


def test_disabled_plugins_produce_no_output(operate, api_client, admin_user, organization_a):
    operate(version="1.0.0")
    operate("disable", 1)
    api_client.force_authenticate(admin_user)
    result = api_client.get(
        "/api/v1/plugins/insights/", HTTP_X_ORGANIZATION_ID=str(organization_a.id)
    )
    assert result.status_code == 200 and result.data == {"results": []}


def test_api_lifecycle_contract(api_client, admin_user, admin_membership, organization_a):
    api_client.force_authenticate(admin_user)
    headers = {"HTTP_X_ORGANIZATION_ID": str(organization_a.id)}
    command = {
        "slug": "stock-alerts",
        "operation": "install",
        "version": "1.0.0",
        "expected_revision": 0,
        "idempotency_key": str(uuid4()),
    }
    response = api_client.post("/api/v1/plugins/commands/", command, format="json", **headers)
    assert response.status_code == 200 and response.data["number"] == 1
    command.update(
        operation="update", version="1.1.0", expected_revision=1, idempotency_key=str(uuid4())
    )
    response = api_client.post("/api/v1/plugins/commands/", command, format="json", **headers)
    assert response.status_code == 200 and response.data["number"] == 2
    command.update(
        operation="rollback", target_revision=1, expected_revision=2, idempotency_key=str(uuid4())
    )
    response = api_client.post("/api/v1/plugins/commands/", command, format="json", **headers)
    assert response.status_code == 200
    assert response.data["snapshot"]["release"]["version"] == "1.0.0"
