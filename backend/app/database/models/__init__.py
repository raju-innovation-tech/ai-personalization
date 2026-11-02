"""
Import every ORM model here so Alembic's autogenerate can discover them
via Base.metadata, and so `from app.database.models import User` works.
"""
from app.database.models.audit_log import AuditLog
from app.database.models.customer import EcommerceCustomer
from app.database.models.event import EventType, Platform, UserEvent
from app.database.models.experiment import Experiment, ExperimentExposure
from app.database.models.offer import Offer, OfferInteraction, OfferRedemption
from app.database.models.product import Product
from app.database.models.recommendation_log import RecommendationLog
from app.database.models.user import User, UserRole

__all__ = [
    "AuditLog",
    "EcommerceCustomer",
    "EventType",
    "Experiment",
    "ExperimentExposure",
    "Offer",
    "OfferInteraction",
    "OfferRedemption",
    "Platform",
    "UserEvent",
    "Product",
    "RecommendationLog",
    "User",
    "UserRole",
]
