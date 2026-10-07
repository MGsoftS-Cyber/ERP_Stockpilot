# Teaching edition: Register the Django application and its model namespace.
from django.apps import AppConfig


class TenancyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.tenancy"

    def ready(self):
        from apps.tenancy import schema  # noqa: F401
