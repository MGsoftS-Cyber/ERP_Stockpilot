# Teaching edition: Model database records, relationships and constraints.
import uuid

from django.conf import settings
from django.db import models


class TimeStampedUUIDModel(models.Model):
    """Stable UUID identity and audit timestamps shared by all domain models."""

    # Stable identifier; UUIDs do not replace permission checks.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Timestamp; automatic dates run during applicable model saves.
    created_at = models.DateTimeField(auto_now_add=True)
    # Timestamp; automatic dates run during applicable model saves.
    updated_at = models.DateTimeField(auto_now=True)

    # Django metadata: schema or API options, not a constructor.
    class Meta:
        abstract = True


class OrganizationScopedQuerySet(models.QuerySet):
    # Construct a tenant-filtered queryset; SQL is normally evaluated later.
    def for_organization(self, organization: object) -> "OrganizationScopedQuerySet":
        return self.filter(organization=organization)


class OrganizationScopedModel(TimeStampedUUIDModel):
    """Base for business data that must never cross an organization boundary."""

    # Many records refer to one parent; on_delete controls deletion behavior.
    organization = models.ForeignKey(
        "tenancy.Organization",
        on_delete=models.PROTECT,
        related_name="%(app_label)s_%(class)s_records",
    )
    # Many records refer to one parent; on_delete controls deletion behavior.
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_%(app_label)s_%(class)s_records",
        null=True,
        blank=True,
    )

    objects = OrganizationScopedQuerySet.as_manager()

    # Django metadata: schema or API options, not a constructor.
    class Meta:
        abstract = True
