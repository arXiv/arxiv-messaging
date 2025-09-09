"""
Pytest configuration and fixtures for arXiv messaging library tests
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from arxiv_messaging import (
    UserPreference, DeliveryMethod, 
    AggregationFrequency, AggregationMethod, Event, EventType
)


@pytest.fixture
def example_user_preferences():
    """Example user preferences for testing"""
    return [
        UserPreference(
            subscription_id="user_123-email",
            user_id="user_123",
            delivery_method=DeliveryMethod.EMAIL,
            aggregation_frequency=AggregationFrequency.DAILY,
            aggregation_method=AggregationMethod.HTML,
            delivery_time="09:00",
            timezone="UTC",
            email_address="user123@arxiv.org"
        ),
        UserPreference(
            subscription_id="user_456-slack",
            user_id="user_456",
            delivery_method=DeliveryMethod.SLACK,
            aggregation_frequency=AggregationFrequency.IMMEDIATE,
            aggregation_method=AggregationMethod.PLAIN,
            timezone="UTC",
            slack_webhook_url="https://hooks.slack.com/triggers/TEST/123456/abcdef123456"
        ),
        UserPreference(
            subscription_id="user_789-email",
            user_id="user_789",
            delivery_method=DeliveryMethod.EMAIL,
            aggregation_frequency=AggregationFrequency.WEEKLY,
            aggregation_method=AggregationMethod.MIME,
            delivery_time="10:00",
            timezone="UTC",
            email_address="user789@arxiv.org"
        ),
        UserPreference(
            subscription_id="user_hourly-slack",
            user_id="user_hourly",
            delivery_method=DeliveryMethod.SLACK,
            aggregation_frequency=AggregationFrequency.HOURLY,
            aggregation_method=AggregationMethod.PLAIN,
            timezone="UTC",
            slack_webhook_url="https://hooks.slack.com/triggers/TEST/789012/xyz789012345"
        )
    ]


@pytest.fixture
def sample_events():
    """Sample events for testing"""
    return [
        Event(
            event_id="event_1",
            user_id="user_123",
            event_type=EventType.NOTIFICATION,
            message="Your submission was processed",
            sender="arxiv-system@arxiv.org",
            subject="arXiv Submission Update",
            timestamp=datetime(2023, 12, 1, 10, 0, 0),
            metadata={"source": "arxiv-submission"}
        ),
        Event(
            event_id="event_2",
            user_id="user_123",
            event_type=EventType.ALERT,
            message="Build completed successfully",
            sender="build-system@arxiv.org", 
            subject="Build Status",
            timestamp=datetime(2023, 12, 1, 11, 0, 0),
            metadata={"build_id": "12345"}
        ),
        Event(
            event_id="event_3",
            user_id="user_456",
            event_type=EventType.NOTIFICATION,
            message="New comment on your paper",
            sender="review-system@arxiv.org",
            subject="Review Update",
            timestamp=datetime(2023, 12, 1, 12, 0, 0),
            metadata={"paper_id": "arxiv-123"}
        )
    ]


