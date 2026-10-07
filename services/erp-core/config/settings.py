# Teaching edition: Configure modules, database access, JWT and allowed browser origins.
import os
from datetime import timedelta
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "development-only-change-me")
DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"
ALLOWED_HOSTS = os.getenv(
    "DJANGO_ALLOWED_HOSTS",
    "localhost,127.0.0.1,backend,testserver",
).split(",")

INSTALLED_APPS = [
    "apps.extensions",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "drf_spectacular",
    "apps.common",
    "apps.tenancy",
    "apps.catalog",
    "apps.partners",
    "apps.inventory",
    "apps.purchasing",
    "apps.sales",  # Week 5: reservation, shipment and customer return workflows.
    "apps.audit.apps.AuditConfig",  # Week 6: append-only cross-module events.
    "apps.billing",
    "apps.finance",
    "apps.intelligence",  # Weeks 7–8: reviewed OCR drafts and advisory forecasts.
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=60,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
LANGUAGES = [("en", "English"), ("fr", "Français"), ("ar", "العربية")]
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "tenancy.User"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "EXCEPTION_HANDLER": "apps.common.exceptions.stockpilot_exception_handler",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": False,
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "StockPilot ERP API",
    "DESCRIPTION": (
        "StockPilot business API: organization access, catalog, inventory, purchasing, "
        "sales, finance, reviewed AI results and plugin management."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "ENUM_NAME_OVERRIDES": {
        "MovementSourceType": "apps.inventory.schema.MOVEMENT_SOURCES",
        "ReservationSourceType": "apps.inventory.schema.RESERVATION_SOURCES",
    },
}

CORS_ALLOWED_ORIGINS = os.getenv(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:5173",
).split(",")
CORS_ALLOW_HEADERS = [
    "accept-language",
    "accept",
    "authorization",
    "content-type",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-organization-id",
]

# Django alone calls the internal AI service. No AI token goes to React.
AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://127.0.0.1:8001")
AI_SERVICE_TOKEN = os.getenv("AI_SERVICE_TOKEN", "")
DATA_UPLOAD_MAX_MEMORY_SIZE = 11 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024

# Week 10: one authentication authority per process; never accept both issuers.
AUTH_MODE = os.getenv("AUTH_MODE", "legacy")
OIDC_ISSUER = os.getenv("OIDC_ISSUER", "http://localhost:9000")
OIDC_JWKS_URL = os.getenv("OIDC_JWKS_URL", f"{OIDC_ISSUER}/oauth2/jwks")
OIDC_AUDIENCE = "stockpilot-api"
if AUTH_MODE not in {"legacy", "oidc"}:
    raise ValueError("AUTH_MODE must be legacy or oidc")
if AUTH_MODE == "oidc":
    REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"] = [
        "apps.tenancy.oidc.SpringAuthentication"
    ]

# Week 11: deployment safety is opt-in and fails closed on demo configuration.
# This does not pretend the development Compose stack is an internet deployment.
if os.getenv("STOCKPILOT_PRODUCTION", "false").lower() == "true":
    from django.core.exceptions import ImproperlyConfigured
    if DEBUG or len(SECRET_KEY) < 40 or AUTH_MODE != "oidc":
        raise ImproperlyConfigured("Production requires DEBUG=false, strong secret and OIDC")
    if not OIDC_ISSUER.startswith("https://") or not AI_SERVICE_TOKEN:
        raise ImproperlyConfigured("Production requires HTTPS identity and an AI service secret")
    if "sqlite" in DATABASES["default"]["ENGINE"] or "*" in ALLOWED_HOSTS:
        raise ImproperlyConfigured("Production requires PostgreSQL and explicit allowed hosts")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_CONTENT_TYPE_NOSNIFF = True
    # Do not trust forwarded headers unless a separately configured trusted proxy strips them.
