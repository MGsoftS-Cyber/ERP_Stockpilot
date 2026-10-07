"""Append-only application audit log; database owners still control the database."""

from django.core.exceptions import ValidationError
from django.db import models

from apps.common.models import OrganizationScopedModel, OrganizationScopedQuerySet


class AppendOnlyQuerySet(OrganizationScopedQuerySet):
    def update(self, **kwargs):
        raise ValidationError("Audit events cannot be changed.")

    def delete(self):
        raise ValidationError("Audit events cannot be deleted.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError("Audit events cannot be changed.")


class AuditEvent(OrganizationScopedModel):
    action = models.CharField(max_length=80)
    entity_type = models.CharField(max_length=80)
    entity_id = models.UUIDField()
    detail = models.JSONField(default=dict)
    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-id"]
        # Week 11: notification polling uses a tenant + newest-event lookup.
        indexes = [models.Index(fields=["organization", "-created_at", "-id"],
                                name="audit_org_recent_idx")]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Append a new event instead of editing history.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Audit events cannot be deleted.")
