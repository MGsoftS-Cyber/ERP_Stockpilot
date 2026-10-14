from django.urls import path
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import mixins, serializers
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter
from rest_framework.views import APIView

from apps.common.api import CurrencyInput, ReasonInput, TenantReadViewSet
from apps.tenancy.services import get_request_membership

from . import selectors, services
from .models import Expense


class ExpenseInput(CurrencyInput):
    idempotency_key = serializers.UUIDField()
    description = serializers.CharField(max_length=240)
    category = serializers.CharField(max_length=80)
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    spent_on = serializers.DateField()


class ExpenseOutput(serializers.ModelSerializer):
    class Meta:
        model = Expense
        fields = ["id", "description", "category", "amount", "currency", "spent_on", "is_void"]


class ExpenseViewSet(mixins.CreateModelMixin, TenantReadViewSet):
    queryset = Expense.objects.all()
    serializer_class = ExpenseOutput

    @extend_schema(request=ExpenseInput, responses=ExpenseOutput)
    def create(self, request):
        obj, created = services.create_expense(**self.command_args(), **self.validate(ExpenseInput))
        return Response(ExpenseOutput(obj).data, status=201 if created else 200)

    @extend_schema(request=ReasonInput, responses=ExpenseOutput)
    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        self.get_object()
        obj = services.void_expense(
            **self.command_args(), expense_id=pk, **self.validate(ReasonInput)
        )
        return Response(ExpenseOutput(obj).data)


class SummaryView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[CurrencyInput],
        responses=inline_serializer(
            "FinanceSummary",
            fields={
                key: serializers.CharField()
                for key in [
                    "currency",
                    "revenue",
                    "cost",
                    "gross_margin",
                    "expenses",
                    "operational_result",
                    "receivables",
                    "payables",
                    "overdue_receivables",
                    "cash_in",
                    "cash_out",
                    "net_cash_flow",
                ]
            },
        ),
    )
    def get(self, request):
        membership = get_request_membership(request)
        options = CurrencyInput(data=request.query_params)
        options.is_valid(raise_exception=True)
        return Response(selectors.summary(membership.organization, **options.validated_data))


router = DefaultRouter()
router.register("expenses", ExpenseViewSet)
urlpatterns = [path("summary/", SummaryView.as_view()), *router.urls]
