# Audit writer: links the actor and organization to a business action and affected record.
# Called inside a service transaction so failed business changes do not leave misleading success
# events.
from .models import AuditEvent


def record(organization, actor, action, entity, **detail):
    # Called within the business transaction: rollback removes the event too.
    return AuditEvent.objects.create(
        organization=organization,
        created_by=actor,
        action=action,
        entity_type=entity._meta.label,
        entity_id=entity.pk,
        detail=detail,
    )
