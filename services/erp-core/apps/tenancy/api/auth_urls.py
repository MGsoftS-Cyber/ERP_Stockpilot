# Teaching edition: Expose login, refresh and current-user API endpoints.
from django.conf import settings
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from apps.tenancy.api.views import CurrentUserView, StockPilotTokenObtainPairView

urlpatterns = [
    path("token/", StockPilotTokenObtainPairView.as_view(), name="token-obtain-pair"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("me/", CurrentUserView.as_view(), name="current-user"),
]

# Week 10: OIDC mode cannot fall back to the temporary password grant.
if settings.AUTH_MODE == "oidc":
    urlpatterns = [path("me/", CurrentUserView.as_view(), name="current-user")]
