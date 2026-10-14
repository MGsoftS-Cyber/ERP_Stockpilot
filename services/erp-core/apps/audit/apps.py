from django.apps import AppConfig


class AuditConfig(AppConfig):
    name = "apps.audit"

    def ready(self):
        # Register event mirrors once Django has loaded all model classes.
        from . import signals  # noqa: F401
