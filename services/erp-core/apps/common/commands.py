# Shared business guardrails: authorization, exact decimals, lock order and conflict responses.
# Purchasing, sales, finance and plugin services reuse these rules inside database transactions.
# API checks improve feedback; service checks also protect calls from scripts/management commands.
"""Shared command rules: authenticate first, then lock and validate business data."""

import hashlib
import json
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from apps.tenancy.models import Membership, Organization

FINANCE_ROLES = ("ADMINISTRATOR", "MANAGER", "ACCOUNTANT")
AI_ROLES = (*FINANCE_ROLES, "PURCHASING_AGENT")


class Conflict(APIException):
    status_code = 409
    default_code = "business_conflict"


def authorize(organization, actor, roles):
    # Services repeat authorization so management commands cannot bypass API checks.
    if (
        not actor.is_active
        or not Membership.objects.filter(
            organization=organization,
            organization__is_active=True,
            user=actor,
            is_active=True,
            role__in=roles,
        ).exists()
    ):
        raise PermissionDenied("Your active membership does not allow this operation.")


def lock_organization(organization):
    # All new financial commands take this lock first: a consistent lock order.
    Organization.objects.select_for_update().get(pk=organization.pk)


def number(value, *, positive=False, places=4):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as error:
        raise ValidationError("An exact decimal is required.") from error
    if not result.is_finite() or result < 0 or (positive and result == 0):
        raise ValidationError(
            "The number must be finite and nonnegative (positive for quantities)."
        )
    if result >= Decimal("1000000000000") or result != result.quantize(Decimal(10) ** -places):
        raise ValidationError(f"At most 12 integer digits and {places} decimal places are allowed.")
    return result


def money(value):
    # This MVP uses two-decimal operational currencies; never use float for money.
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def replay(model, organization, key, payload_hash):
    previous = model.objects.filter(organization=organization, idempotency_key=key).first()
    if previous and previous.payload_hash != payload_hash:
        raise Conflict("This idempotency key was already used with different input.")
    return previous
