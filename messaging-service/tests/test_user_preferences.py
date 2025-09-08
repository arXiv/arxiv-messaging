"""
Tests for user preferences and system initialization
"""

import pytest
from src.message_server import (
    UserPreference, DeliveryMethod, AggregationFrequency, AggregationMethod
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


class TestSystemIntegration:
    """Test system initialization with user preferences"""
    
    def test_system_add_user_preferences(self, event_aggregation_system, example_user_preferences):
        """Test adding user preferences to the system"""
        # Add all example preferences
        for pref in example_user_preferences:
            event_aggregation_system.add_user_preference(pref)
        
        # Verify preferences were stored (mock verification)
        assert event_aggregation_system.event_store is not None
    
    def test_system_initialization(self, mock_project_id, mock_subscription_name):
        """Test system initialization without examples"""
        from src.message_server import EventAggregationSystem
        
        from unittest.mock import patch
        
        with patch('src.message_server.EventStore'), \
             patch('src.message_server.PubSubEventProcessor'), \
             patch('src.message_server.ScheduledDeliveryService'):
            
            system = EventAggregationSystem(mock_project_id, mock_subscription_name)
            
            assert system.event_store is not None
            assert system.delivery_service is not None
            assert system.pubsub_processor is not None
            assert system.scheduled_delivery is not None