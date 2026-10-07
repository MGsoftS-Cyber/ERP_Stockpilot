from django.apps import AppConfig


class SalesConfig(AppConfig):
    # Django discovers models and migrations under this application path.
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.sales"
