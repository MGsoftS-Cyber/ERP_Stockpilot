# Teaching edition: Convert records to JSON and validate incoming API values.
from rest_framework import serializers

from apps.partners.models import BusinessPartner


class BusinessPartnerSerializer(serializers.ModelSerializer):
    partner_type_label = serializers.CharField(source="get_partner_type_display", read_only=True)

    # Django metadata: schema or API options, not a constructor.
    class Meta:
        model = BusinessPartner
        fields = [
            "id",
            "code",
            "name",
            "partner_type",
            "partner_type_label",
            "email",
            "phone",
            "address",
            "tax_identifier",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
