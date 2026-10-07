# Plugin lifecycle: commands check authorization, expected revision and idempotency before changing
# state.
# Installation, immutable history and audit event commit together or roll back together.
# Rollback restores an older plugin snapshot as a new revision, never reversing ERP transactions.
"""atomic lifecycle, optimistic revisions, idempotency and reversible configuration.

Rollback restores manifest/configuration/enabled state as a NEW revision. It never
reverses stock, invoices or database migrations. Hook packages cannot define SQL or code.
"""

from django.db import transaction
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from apps.audit.services import record
from apps.common.commands import Conflict, authorize, digest, lock_organization
from apps.extensions import hooks, registry
from apps.extensions.models import Installation, Revision


def snapshot(installation):
    return {
        "release": installation.release,
        "checksum": installation.checksum,
        "configuration": installation.configuration,
        "enabled": installation.enabled,
    }


def dependencies(organization, candidate):
    installed = {p.slug: p for p in Installation.objects.filter(organization=organization)}
    installed[candidate.slug] = candidate

    def visit(slug, path):
        if slug in path:
            raise Conflict("Circular plugin dependencies are not supported")
        item = installed.get(slug)
        if item and item.enabled:
            for child in item.release["requires"]:
                visit(child, path | {slug})

    for slug in installed:
        visit(slug, set())
    for plugin in installed.values():
        if not plugin.enabled:
            continue
        for slug, minimum in plugin.release["requires"].items():
            dependency = installed.get(slug)
            if (
                not dependency
                or not dependency.enabled
                or registry.version(dependency.release["version"]) < registry.version(minimum)
            ):
                raise Conflict(f"{plugin.slug} requires enabled {slug} >= {minimum}")


@transaction.atomic
def change(*, organization, actor, command):
    authorize(organization, actor, ("ADMINISTRATOR",))
    grants = getattr(actor, "oidc_org_roles", None)
    if grants is not None and grants.get(str(organization.pk)) != "ADMINISTRATOR":
        raise PermissionDenied("Identity does not grant plugin administration")
    lock_organization(organization)  # Serializes installs and dependency changes on PostgreSQL.
    payload_hash = digest(command)
    previous = Revision.objects.filter(
        organization=organization, idempotency_key=command["idempotency_key"]
    ).first()
    if previous:
        if previous.payload_hash != payload_hash:
            raise Conflict("Idempotency key already used for another command")
        return previous
    plugin = Installation.objects.filter(organization=organization, slug=command["slug"]).first()
    expected = command["expected_revision"]
    if (plugin.revision if plugin else 0) != expected:
        raise Conflict("Plugin changed. Refresh and use the current revision")
    action = command["operation"]
    if action == "install":
        if plugin:
            raise Conflict("Plugin is already installed; enable or update it")
        selected = registry.resolve(command["slug"], command["version"])
        plugin = Installation(
            organization=organization,
            slug=command["slug"],
            created_by=actor,
            release=selected["manifest"],
            checksum=selected["checksum"],
            revision=0,
        )
        plugin.configuration = plugin.release["settings"].copy()
    elif not plugin:
        raise ValidationError("Install the plugin first")
    elif action == "update":
        selected = registry.resolve(plugin.slug, command["version"])
        if registry.version(selected["manifest"]["version"]) <= registry.version(
            plugin.release["version"]
        ):
            raise Conflict("Updates must increase the version; use rollback for older state")
        plugin.release, plugin.checksum = selected["manifest"], selected["checksum"]
        # Preserve user settings; incompatible configuration aborts the entire operation.
    elif action == "rollback":
        target = plugin.history.filter(
            number=command["target_revision"], number__lt=plugin.revision
        ).first()
        if not target:
            raise ValidationError("Choose an earlier revision of this installation")
        for key, value in target.snapshot.items():
            setattr(plugin, key, value)
    elif action in {"enable", "disable"}:
        plugin.enabled = action == "enable"
    elif action != "configure":
        raise ValidationError("Unknown lifecycle operation")
    registry.validate(plugin.release)
    if registry.checksum(plugin.release) != plugin.checksum:
        raise Conflict("Stored release checksum failed")
    if "configuration" in command:
        plugin.configuration = command["configuration"]
    plugin.configuration = registry.configuration(plugin.release, plugin.configuration)
    dependencies(organization, plugin)
    if plugin.enabled:
        try:
            hooks.execute(plugin.release, plugin.configuration, organization)
        except Exception as error:
            failure = APIException("Plugin health check failed; no changes were saved")
            failure.status_code = 503
            raise failure from error
    plugin.revision += 1
    plugin.save()
    revision = Revision.objects.create(
        organization=organization,
        created_by=actor,
        installation=plugin,
        number=plugin.revision,
        operation=action,
        snapshot=snapshot(plugin),
        idempotency_key=command["idempotency_key"],
        payload_hash=payload_hash,
    )
    record(
        organization=organization,
        actor=actor,
        action=f"plugin.{action}",
        entity=plugin,
        detail={"slug": plugin.slug, "revision": plugin.revision},
    )
    return revision
