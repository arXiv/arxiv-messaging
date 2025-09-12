"""
Tests for user preferences and system initialization
"""

import pytest
import sys
import os

# Add the project root to the path so we can import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arxiv_messaging import (
    UserPreference, DeliveryMethod, AggregationFrequency, AggregationMethod, EventType
)


class TestUserPreferences:
    """Test user preference creation and validation"""
    
    def test_email_daily_html_preference(self, example_user_preferences):
        """Test email user with daily HTML aggregation"""
        email_user = example_user_preferences[0]
        
        assert email_user.user_id == "user_123"
        assert email_user.delivery_method == DeliveryMethod.EMAIL
        assert email_user.aggregation_frequency == AggregationFrequency.DAILY
        assert email_user.aggregation_method == AggregationMethod.HTML
        assert email_user.delivery_time == "09:00"
        assert email_user.timezone == "UTC"
        assert email_user.email_address == "user123@arxiv.org"
    
    def test_slack_immediate_plain_preference(self, example_user_preferences):
        """Test Slack user with immediate plain text delivery"""
        slack_user = example_user_preferences[1]
        
        assert slack_user.user_id == "user_456"
        assert slack_user.delivery_method == DeliveryMethod.SLACK
        assert slack_user.aggregation_frequency == AggregationFrequency.IMMEDIATE
        assert slack_user.aggregation_method == AggregationMethod.PLAIN
        assert slack_user.timezone == "UTC"
        assert slack_user.slack_webhook_url == "https://hooks.slack.com/triggers/TEST/123456/abcdef123456"
        assert slack_user.email_address is None
    
    def test_email_weekly_mime_preference(self, example_user_preferences):
        """Test email user with weekly MIME aggregation"""
        weekly_user = example_user_preferences[2]
        
        assert weekly_user.user_id == "user_789"
        assert weekly_user.delivery_method == DeliveryMethod.EMAIL
        assert weekly_user.aggregation_frequency == AggregationFrequency.WEEKLY
        assert weekly_user.aggregation_method == AggregationMethod.MIME
        assert weekly_user.delivery_time == "10:00"
        assert weekly_user.email_address == "user789@arxiv.org"
    
    def test_slack_hourly_plain_preference(self, example_user_preferences):
        """Test Slack user with hourly plain text delivery"""
        hourly_user = example_user_preferences[3]
        
        assert hourly_user.user_id == "user_hourly"
        assert hourly_user.delivery_method == DeliveryMethod.SLACK
        assert hourly_user.aggregation_frequency == AggregationFrequency.HOURLY
        assert hourly_user.aggregation_method == AggregationMethod.PLAIN
        assert hourly_user.slack_webhook_url == "https://hooks.slack.com/triggers/TEST/789012/xyz789012345"
    
    def test_all_aggregation_frequencies_covered(self, example_user_preferences):
        """Test that example preferences cover all aggregation frequencies"""
        frequencies = {pref.aggregation_frequency for pref in example_user_preferences}
        
        assert AggregationFrequency.IMMEDIATE in frequencies
        assert AggregationFrequency.HOURLY in frequencies
        assert AggregationFrequency.DAILY in frequencies
        assert AggregationFrequency.WEEKLY in frequencies
    
    def test_all_aggregation_methods_covered(self, example_user_preferences):
        """Test that example preferences cover all aggregation methods"""
        methods = {pref.aggregation_method for pref in example_user_preferences}
        
        assert AggregationMethod.PLAIN in methods
        assert AggregationMethod.HTML in methods
        assert AggregationMethod.MIME in methods
    
    def test_delivery_method_combinations(self, example_user_preferences):
        """Test valid delivery method and aggregation combinations"""
        for pref in example_user_preferences:
            if pref.delivery_method == DeliveryMethod.EMAIL:
                assert pref.email_address is not None
                # Email can use any aggregation method
                assert pref.aggregation_method in [
                    AggregationMethod.PLAIN, 
                    AggregationMethod.HTML, 
                    AggregationMethod.MIME
                ]
            
            elif pref.delivery_method == DeliveryMethod.SLACK:
                assert pref.slack_webhook_url is not None
                assert pref.email_address is None
                # Slack typically uses plain or HTML
                assert pref.aggregation_method in [
                    AggregationMethod.PLAIN,
                    AggregationMethod.HTML
                ]


class TestLibraryComponents:
    """Test library components and data structures"""
    
    def test_subscription_creation_validation(self):
        """Test subscription creation and validation"""
        from arxiv_messaging import Subscription, DeliveryErrorStrategy
        
        # Test creating a subscription with all parameters
        subscription = Subscription(
            subscription_id="test-subscription",
            user_id="test-user",
            delivery_method=DeliveryMethod.EMAIL,
            aggregation_frequency=AggregationFrequency.DAILY,
            aggregation_method=AggregationMethod.HTML,
            delivery_error_strategy=DeliveryErrorStrategy.RETRY,
            delivery_time="10:00",
            timezone="EST",
            email_address="test@example.com",
            enabled=True
        )
        
        assert subscription.subscription_id == "test-subscription"
        assert subscription.user_id == "test-user"
        assert subscription.delivery_method == DeliveryMethod.EMAIL
        assert subscription.aggregation_frequency == AggregationFrequency.DAILY
        assert subscription.aggregation_method == AggregationMethod.HTML
        assert subscription.delivery_error_strategy == DeliveryErrorStrategy.RETRY
        assert subscription.delivery_time == "10:00"
        assert subscription.timezone == "EST"
        assert subscription.email_address == "test@example.com"
        assert subscription.enabled is True
    
    def test_event_creation(self):
        """Test event creation and validation"""
        from arxiv_messaging import Event
        from datetime import datetime
        
        event = Event(
            event_id="test-event-123",
            user_id="test-user",
            event_type=EventType.ALERT,
            message="Test alert message",
            sender="test@example.com",
            subject="Test Alert",
            timestamp=datetime.now(),
            metadata={"source": "test", "priority": "high"}
        )
        
        assert event.event_id == "test-event-123"
        assert event.user_id == "test-user"
        assert event.event_type == EventType.ALERT
        assert event.message == "Test alert message"
        assert event.sender == "test@example.com"
        assert event.subject == "Test Alert"
        assert event.metadata["source"] == "test"
        assert event.metadata["priority"] == "high"
    
    def test_event_type_enum_values(self):
        """Test EventType enum values"""
        assert EventType.NOTIFICATION.value == "NOTIFICATION"
        assert EventType.ALERT.value == "ALERT"
        assert EventType.WARNING.value == "WARNING"
        assert EventType.INFO.value == "INFO"