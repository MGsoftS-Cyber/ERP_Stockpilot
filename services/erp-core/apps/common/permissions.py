# Teaching edition: Enforce permissions on the server, not just in visible buttons.
from collections.abc import Iterable

from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.tenancy.models import Membership
from apps.tenancy.services import get_request_membership


class TenantRolePermission(BasePermission):
    """Require active organization membership and role-based write access."""

    message = "You do not have permission for this action in the selected organization."

    # Allow member reads, then enforce configured write roles.
    def has_permission(self, request, view) -> bool:
        membership = get_request_membership(request)
        if request.method in SAFE_METHODS:
            return True

        write_roles: Iterable[str] = getattr(
            view,
            "write_roles",
            (Membership.Role.ADMINISTRATOR, Membership.Role.MANAGER),
        )
        return membership.role in write_roles
