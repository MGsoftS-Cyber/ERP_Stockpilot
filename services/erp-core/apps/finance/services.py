from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.audit.services import record
from apps.common.commands import FINANCE_ROLES, authorize, digest, lock_organization, number, replay

from .models import Expense


@transaction.atomic
def create_expense(
    *, organization, actor, idempotency_key, description, category, amount, currency, spent_on
):
    authorize(organization, actor, FINANCE_ROLES)
    lock_organization(organization)
    amount = number(amount, positive=True, places=2)
    if currency not in ("DZD", "EUR", "USD") or not description.strip() or not category.strip():
        raise ValidationError("Choose a supported currency and supply description/category.")
    data = dict(
        description=description,
        category=category,
        amount=format(amount, ".2f"),
        currency=currency,
        spent_on=spent_on,
    )
    payload_hash = digest(data)
    previous = replay(Expense, organization, idempotency_key, payload_hash)
    if previous:
        return previous, False
    expense = Expense.objects.create(
        organization=organization,
        created_by=actor,
        idempotency_key=idempotency_key,
        payload_hash=payload_hash,
        **data,
    )
    record(organization, actor, "finance.expense_created", expense, amount=str(amount))
    return expense, True


@transaction.atomic
def void_expense(*, organization, actor, expense_id, reason):
    authorize(organization, actor, FINANCE_ROLES)
    lock_organization(organization)
    expense = Expense.objects.filter(organization=organization, pk=expense_id).first()
    if expense is None or not reason.strip():
        raise ValidationError("An existing expense and a reason are required.")
    if not expense.is_void:
        expense.is_void = True
        expense.save(update_fields=["is_void", "updated_at"])
        record(organization, actor, "finance.expense_void", expense, reason=reason)
    return expense
