"""Export UUIDs, Django password hashes and organization grants, never plaintext passwords.

This sensitive snapshot is an explicit migration/sync boundary, not an admin API.
Run again after user/role changes, then restart identity. Do not commit the output.
Identity only grants roles that also match an active local Django membership.
"""
import json
import os
from pathlib import Path

from django.core.management.base import BaseCommand

from apps.tenancy.models import User


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("destination")

    def handle(self, *args, **options):
        destination = Path(options["destination"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        records = []
        users = User.objects.filter(is_active=True).prefetch_related("memberships__organization")
        for user in users:
            records.append({
                "id": str(user.id), "email": user.email, "password": user.password,
                "roles": {str(m.organization_id): m.role for m in user.memberships.all()
                          if m.is_active and m.organization.is_active},
            })
        temporary = destination.with_suffix(".tmp")
        # chmod is necessary even if a previous temporary file already exists.
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(records, stream)
        temporary.replace(destination)
        self.stdout.write(f"Exported {len(records)} identities; protect the private snapshot.")
