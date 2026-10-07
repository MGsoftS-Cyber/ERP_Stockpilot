from django.db import models
from django.db.models import Q

from apps.common.models import OrganizationScopedModel


class Expense(OrganizationScopedModel):
    # Expenses here mean cash expenses; supplier invoice settlement is separate.
    description = models.CharField(max_length=240)
    category = models.CharField(max_length=80)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    currency = models.CharField(max_length=3)
    spent_on = models.DateField()
    is_void = models.BooleanField(default=False)
    idempotency_key = models.UUIDField()
    payload_hash = models.CharField(max_length=64)

    class Meta:
        ordering = ["-spent_on", "-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "idempotency_key"], name="expense_key"),
            models.CheckConstraint(condition=Q(amount__gt=0), name="expense_positive"),
        ]
