# Token verification: validates Spring access-token issuer, audience, signature and expiry.
# Signed organization grants must agree with Django membership records before ERP access is allowed.
# It authenticates identity; inventory and financial services still enforce their own operation
# rules.
"""validate Spring access tokens; never trust browser-supplied roles."""
from functools import lru_cache
from uuid import UUID

import jwt
from django.conf import settings
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from apps.tenancy.models import Membership, User


@lru_cache(maxsize=4)
def key_client(url):
    # Pin the JWKS URL in configuration, never follow a token's jku/x5u header.
    return jwt.PyJWKClient(url, cache_jwk_set=True, lifespan=60, timeout=3)


class SpringAuthentication(BaseAuthentication):
    def authenticate_header(self, request):
        return "Bearer"

    def authenticate(self, request):
        parts = get_authorization_header(request).split()
        if not parts:
            return None
        if len(parts) != 2 or parts[0].lower() != b"bearer":
            raise AuthenticationFailed("A Bearer access token is required.")
        try:
            token = parts[1].decode("ascii")
            key = key_client(settings.OIDC_JWKS_URL).get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token, key, algorithms=["RS256"], audience=settings.OIDC_AUDIENCE,
                issuer=settings.OIDC_ISSUER,
                options={"require": ["exp", "iat", "sub", "iss", "aud"]},
            )
            scopes = claims.get("scope", [])
            if isinstance(scopes, str):
                scopes = scopes.split()
            if (claims.get("token_use") != "access" or not isinstance(scopes, list)
                    or "erp" not in scopes):
                raise ValueError("Not an ERP access token")
            user_id = UUID(claims["sub"])
            grants = claims.get("org_roles")
            if not isinstance(grants, dict):
                raise ValueError("Missing organization grants")
            user = User.objects.get(pk=user_id, is_active=True)
            # Intersection, not union: local revocations take effect immediately.
            # A role change must be synchronized to identity; a mismatch fails closed.
            user.oidc_org_roles = {
                str(m.organization_id): m.role
                for m in Membership.objects.filter(user=user, is_active=True,
                                                    organization__is_active=True)
                if grants.get(str(m.organization_id)) == m.role
            }
            return user, claims
        except (jwt.PyJWTError, ValueError, TypeError, UnicodeError, User.DoesNotExist) as exc:
            raise AuthenticationFailed("Invalid or unavailable identity credentials.") from exc
