from django.http import FileResponse
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter

from apps.billing.api import LineInput
from apps.common.api import CurrencyInput, EmptyInput, TenantReadViewSet
from apps.common.commands import AI_ROLES

from . import services
from .models import OCRDocument, RecommendationRun


class UploadInput(serializers.Serializer):
    file = serializers.FileField(max_length=240)


class ReviewInput(CurrencyInput):
    partner_id = serializers.UUIDField()
    reference = serializers.CharField(max_length=64)
    issued_on = serializers.DateField()
    due_on = serializers.DateField()
    lines = LineInput(many=True, allow_empty=False, max_length=100)


class OCROutput(serializers.ModelSerializer):
    class Meta:
        model = OCRDocument
        # Storage paths are private; use the authenticated download action.
        fields = [
            "id",
            "original_name",
            "sha256",
            "status",
            "extraction",
            "correction",
            "error",
            "invoice",
            "created_at",
        ]


class ForecastInput(serializers.Serializer):
    product_id = serializers.UUIDField()
    warehouse_id = serializers.UUIDField()
    lead_time_days = serializers.IntegerField(min_value=1, max_value=90)
    horizon_days = serializers.IntegerField(min_value=1, max_value=90)


class DecisionInput(serializers.Serializer):
    decision = serializers.ChoiceField(choices=["ACCEPTED", "REJECTED"])
    note = serializers.CharField(max_length=2000)


class RunOutput(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)

    class Meta:
        model = RecommendationRun
        fields = [
            "id",
            "product",
            "warehouse",
            "product_name",
            "warehouse_name",
            "inputs",
            "result",
            "status",
            "error",
            "decision",
            "decision_note",
            "decided_by",
            "decided_at",
            "created_at",
        ]


class OCRViewSet(TenantReadViewSet):
    queryset = OCRDocument.objects.all()
    serializer_class = OCROutput
    write_roles = AI_ROLES

    @extend_schema(request=UploadInput, responses=OCROutput)
    @action(detail=False, methods=["post"], parser_classes=[MultiPartParser, FormParser])
    def upload(self, request):
        obj = services.upload_document(**self.command_args(), **self.validate(UploadInput))
        return Response(OCROutput(obj).data, status=201)

    @extend_schema(request=EmptyInput, responses=OCROutput)
    @action(detail=True, methods=["post"])
    def extract(self, request, pk=None):
        self.get_object()
        obj = services.extract(**self.command_args(), document_id=pk)
        return Response(OCROutput(obj).data)

    @extend_schema(request=ReviewInput, responses=OCROutput)
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        self.get_object()
        obj = services.approve_document(
            **self.command_args(), document_id=pk, corrected=self.validate(ReviewInput)
        )
        return Response(OCROutput(obj).data)

    @extend_schema(responses=bytes)
    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        document = self.get_object()
        response = FileResponse(
            document.file.open("rb"),
            as_attachment=True,
            filename=document.original_name,
            content_type="application/octet-stream",
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "no-store"
        return response


class ForecastViewSet(mixins.CreateModelMixin, TenantReadViewSet):
    queryset = RecommendationRun.objects.select_related("product", "warehouse")
    serializer_class = RunOutput
    write_roles = AI_ROLES

    @extend_schema(request=ForecastInput, responses=RunOutput)
    def create(self, request):
        obj = services.run_forecast(**self.command_args(), **self.validate(ForecastInput))
        return Response(RunOutput(obj).data, status=201)

    @extend_schema(request=DecisionInput, responses=RunOutput)
    @action(detail=True, methods=["post"])
    def decide(self, request, pk=None):
        self.get_object()
        obj = services.decide(**self.command_args(), run_id=pk, **self.validate(DecisionInput))
        return Response(RunOutput(obj).data)


router = DefaultRouter()
router.register("documents", OCRViewSet)
router.register("forecasts", ForecastViewSet)
urlpatterns = router.urls
