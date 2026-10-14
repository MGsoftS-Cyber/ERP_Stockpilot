# Model database records, relationships and constraints.
import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q

from apps.common.models import TimeStampedUUIDModel
from apps.tenancy.managers import UserManager


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = None
    # Email-shaped text; account creation and uniqueness are separate rules.
    email = models.EmailField(unique=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    # Return a readable label for admin and debugging without modifying data.
    def __str__(self) -> str:
        return self.email


class Organization(TimeStampedUUIDModel):
    name = models.CharField(max_length=160)
    # URL-friendly identifier, distinct from the human-readable name.
    slug = models.SlugField(max_length=80, unique=True)
    is_active = models.BooleanField(default=True)
    class Meta:
        ordering = ["name"]

    # Return a readable label for admin and debugging without modifying data.
    def __str__(self) -> str:
        return self.name


class Membership(TimeStampedUUIDModel):
    class Role(models.TextChoices):
        ADMINISTRATOR = "ADMINISTRATOR", "Administrator"
        MANAGER = "MANAGER", "Manager"
        STOCK_OPERATOR = "STOCK_OPERATOR", "Stock operator"
        PURCHASING_AGENT = "PURCHASING_AGENT", "Purchasing agent"
        SALES_AGENT = "SALES_AGENT", "Sales agent"
        ACCOUNTANT = "ACCOUNTANT", "Accountant"
        VIEWER = "VIEWER", "Read-only viewer"
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=32, choices=Role.choices)
    is_active = models.BooleanField(default=True)
    class Meta:
        ordering = ["organization__name", "user__email"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "user"],
                name="unique_organization_user_membership",
            ),
            models.CheckConstraint(
                condition=Q(
                    role__in=[
                        "ADMINISTRATOR",
                        "MANAGER",
                        "STOCK_OPERATOR",
                        "PURCHASING_AGENT",
                        "SALES_AGENT",
                        "ACCOUNTANT",
                        "VIEWER",
                    ]
                ),
                name="membership_role_is_valid",
            ),
        ]

    # Return a readable label for admin and debugging without modifying data.
    def __str__(self) -> str:
        return f"{self.user.email} - {self.organization.name} ({self.get_role_display()})"
