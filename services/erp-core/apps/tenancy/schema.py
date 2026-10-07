"""Describe bearer credentials without exposing the internal JWKS address."""
from drf_spectacular.extensions import OpenApiAuthenticationExtension


class SpringAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "apps.tenancy.oidc.SpringAuthentication"
    name = "springAccessToken"

    def get_security_definition(self, auto_schema):
        return {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
