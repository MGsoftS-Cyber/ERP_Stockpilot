from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.inventory.models import StockMovement
from apps.purchasing.models import PurchaseEvent
from apps.sales.models import SalesEvent

from .services import record


@receiver(post_save, sender=PurchaseEvent)
@receiver(post_save, sender=SalesEvent)
def mirror_business_event(sender, instance, created, raw=False, **kwargs):
    # Existing Week 4/5 services already produce events inside their transactions.
    if created and not raw:
        record(
            instance.organization,
            instance.created_by,
            f"{sender._meta.app_label}.{instance.action}",
            instance.order,
            message=instance.detail,
        )


@receiver(post_save, sender=StockMovement)
def mirror_movement(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        record(
            instance.organization,
            instance.created_by,
            "inventory.movement",
            instance,
            quantity=str(instance.quantity_signed),
            movement_type=instance.movement_type,
        )
