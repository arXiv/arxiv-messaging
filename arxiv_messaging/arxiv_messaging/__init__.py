"""ArXiv Messaging Library

Common interfaces and utilities for the ArXiv messaging system.
"""

from .event_type import (
    EventType, 
    DeliveryMethod, 
    AggregationFrequency, 
    AggregationMethod, 
    DeliveryErrorStrategy, 
    Subscription, 
    UserPreference, 
    Event
)
from .send_notification import send_notification
from .firebase_loader import FirebaseLoader

__version__ = "0.1.0"
__all__ = [
    "EventType", 
    "DeliveryMethod", 
    "AggregationFrequency", 
    "AggregationMethod", 
    "DeliveryErrorStrategy", 
    "Subscription", 
    "UserPreference", 
    "Event",
    "send_notification", 
    "FirebaseLoader"
]