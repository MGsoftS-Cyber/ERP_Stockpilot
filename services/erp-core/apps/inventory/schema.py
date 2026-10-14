"""Distinct OpenAPI names for two different source_type choice sets."""
from .models import StockMovement, StockReservation

MOVEMENT_SOURCES = StockMovement.SourceType.choices
RESERVATION_SOURCES = StockReservation.SourceType.choices
