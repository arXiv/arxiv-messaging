from enum import Enum
from dataclasses import dataclass
from typing import Dict, Any, Optional
from datetime import datetime

# Event types for messaging system
class EventType(Enum):
    NOTIFICATION = "NOTIFICATION"
    ALERT = "ALERT"
    WARNING = "WARNING"
    INFO = "INFO"

class DeliveryMethod(Enum):
    EMAIL = "email"
    SLACK = "slack"

class AggregationFrequency(Enum):
    IMMEDIATE = "immediate"
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"

class AggregationMethod(Enum):
    PLAIN = "plain"
    MIME = "MIME" 
    HTML = "HTML"

class DeliveryErrorStrategy(Enum):
    RETRY = "retry"      # Retry on delivery failure (guaranteed delivery)
    IGNORE = "ignore"    # Ignore delivery failures (avoid spam/duplicates)

@dataclass
class Subscription:
    subscription_id: str  # Unique identifier for this subscription
    user_id: str          # User who owns this subscription
    delivery_method: DeliveryMethod
    aggregation_frequency: AggregationFrequency
    aggregation_method: AggregationMethod = AggregationMethod.PLAIN
    delivery_error_strategy: DeliveryErrorStrategy = DeliveryErrorStrategy.RETRY
    delivery_time: str = "09:00"  # Format: HH:MM
    timezone: str = "UTC"
    email_address: Optional[str] = None
    slack_webhook_url: Optional[str] = None
    enabled: bool = True  # Allow disabling subscriptions without deleting

# Backward compatibility alias
UserPreference = Subscription

@dataclass
class Event:
    event_id: str
    user_id: str
    event_type: EventType
    message: str
    sender: str
    subject: str
    timestamp: datetime
    metadata: Dict[str, Any]
