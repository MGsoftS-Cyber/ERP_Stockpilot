"""Week 13: organization-owned plugin state; immutable history is the rollback source."""

from django.db import models

from apps.audit.models import AppendOnlyQuerySet
from apps.common.models import OrganizationScopedModel


class Installation(OrganizationScopedModel):
    slug = models.SlugField(max_length=64)
    release = models.JSONField()  # Validated manifest snapshot, never executable code.
    checksum = models.CharField(max_length=64)
    configuration = models.JSONField(default=dict)
    enabled = models.BooleanField(default=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "slug"], name="extension_org_slug_unique"
            )
        ]


class MarketplaceRelease(OrganizationScopedModel):
    """A publisher-owned submission. Only approved manifests enter the catalog."""

    slug = models.SlugField(max_length=64)
    version = models.CharField(max_length=20)
    manifest = models.JSONField()
    checksum = models.CharField(max_length=64)
    summary = models.CharField(max_length=240)
    status = models.CharField(
        max_length=16,
        default="pending",
        choices=[("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected")],
    )
    review_note = models.CharField(max_length=500, blank=True)
    reviewed_by = models.ForeignKey(
        "tenancy.User", null=True, on_delete=models.PROTECT, related_name="reviewed_plugins"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["slug", "version"], name="marketplace_release_unique")
        ]


class Appearance(OrganizationScopedModel):
    settings = models.JSONField(default=dict)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organization"], name="appearance_org_unique")
        ]


class Revision(OrganizationScopedModel):
    objects = AppendOnlyQuerySet.as_manager()
    installation = models.ForeignKey(Installation, on_delete=models.PROTECT, related_name="history")
    number = models.PositiveIntegerField()
    operation = models.CharField(max_length=16)
    snapshot = models.JSONField()
    idempotency_key = models.UUIDField()
    payload_hash = models.CharField(max_length=64)

    class Meta:
        ordering = ["-number"]
        constraints = [
            models.UniqueConstraint(
                fields=["installation", "number"], name="extension_revision_unique"
            ),
            models.UniqueConstraint(
                fields=["organization", "idempotency_key"], name="extension_key_unique"
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Plugin history is append-only")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Plugin history is retained for rollback")
