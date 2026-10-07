# Tenant boundary: X-Organization-ID selects a company, not permission to access it.
# This resolver checks active membership and OIDC grants, then shares the result with
# serializers/views.
# Query filtering and service authorization use the same validated organization.
# Teaching edition: Perform business operations after checking the tenant and input.
from uuid import UUID

from rest_framework.exceptions import NotAuthenticated, PermissionDenied, ValidationError

from apps.tenancy.models import Membership


# Validate the organization header and cache the checked membership.
def get_request_membership(request) -> Membership:
    """Resolve and cache the active membership selected by X-Organization-ID."""

    cached = getattr(request, "stockpilot_membership", None)
    if cached is not None:
        return cached

    if not request.user or not request.user.is_authenticated:
        raise NotAuthenticated()

    raw_organization_id = request.headers.get("X-Organization-ID")
    if not raw_organization_id:
        raise ValidationError({"X-Organization-ID": "This header is required."})

    try:
        organization_id = UUID(raw_organization_id)
    except (TypeError, ValueError) as exc:
        raise ValidationError({"X-Organization-ID": "Must be a valid UUID."}) from exc

    try:
        membership = Membership.objects.select_related("organization").get(
            user=request.user,
            organization_id=organization_id,
            is_active=True,
            organization__is_active=True,
        )
    except Membership.DoesNotExist as exc:
        raise PermissionDenied("You are not a member of the selected organization.") from exc

    grants = getattr(request.user, "oidc_org_roles", None)
    if grants is not None and grants.get(str(organization_id)) != membership.role:
        raise PermissionDenied("Identity and ERP organization grants do not match.")

    request.stockpilot_membership = membership
    request.organization = membership.organization
    return membership
