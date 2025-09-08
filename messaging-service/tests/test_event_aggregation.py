"""
Tests for event aggregation methods
"""

import pytest
from src.message_server import EventAggregator, AggregationMethod


class TestEventAggregation:
    """Test event aggregation with different methods"""
    
    @pytest.fixture
    def event_aggregator(self, mock_event_store):
        """EventAggregator instance for testing"""
        return EventAggregator(mock_event_store)
    
    def test_plain_aggregation(self, event_aggregator, sample_events):
        """Test plain text aggregation"""
        user_events = [event for event in sample_events if event.user_id == "user_123"]
        
        result = event_aggregator.aggregate_events("user_123", user_events, AggregationMethod.PLAIN)
        
        assert "Event Summary for User user_123" in result
        assert "Total Events: 2" in result
        assert "NOTIFICATION" in result
        assert "ALERT" in result
        assert "Your submission was processed" in result
        assert "Build completed successfully" in result
    
    def test_html_aggregation(self, event_aggregator, sample_events):
        """Test HTML table aggregation"""
        user_events = [event for event in sample_events if event.user_id == "user_123"]
        
        result = event_aggregator.aggregate_events("user_123", user_events, AggregationMethod.HTML)
        
        assert "<!DOCTYPE html>" in result
        assert "<table>" in result
        assert "<th>Timestamp</th>" in result
        assert "<th>Event ID</th>" in result
        assert "<th>Sender</th>" in result
        assert "<th>Subject</th>" in result
        assert "Event Summary for User user_123" in result
        assert "arxiv-system@arxiv.org" in result
        assert "build-system@arxiv.org" in result
    
    def test_mime_aggregation(self, event_aggregator, sample_events):
        """Test MIME multipart aggregation"""
        user_events = [event for event in sample_events if event.user_id == "user_123"]
        
        result = event_aggregator.aggregate_events("user_123", user_events, AggregationMethod.MIME)
        
        assert "Content-Type: multipart/mixed" in result
        assert "Subject: Event Summary for User user_123" in result
        assert "From: arXiv Messaging System" in result
        assert 'Content-Disposition: inline; filename="summary.txt"' in result
        assert 'Content-Disposition: inline; filename="NOTIFICATION_events.txt"' in result
        assert 'Content-Disposition: inline; filename="ALERT_events.txt"' in result
    
    def test_empty_events_list(self, event_aggregator):
        """Test aggregation with empty events list"""
        result = event_aggregator.aggregate_events("user_123", [], AggregationMethod.PLAIN)
        assert result == ""
        
        result = event_aggregator.aggregate_events("user_123", [], AggregationMethod.HTML)
        assert result == ""
        
        result = event_aggregator.aggregate_events("user_123", [], AggregationMethod.MIME)
        assert result == ""
    
    def test_single_event_aggregation(self, event_aggregator, sample_events):
        """Test aggregation with single event"""
        single_event = [sample_events[0]]
        
        result = event_aggregator.aggregate_events("user_123", single_event, AggregationMethod.PLAIN)
        
        assert "Total Events: 1" in result
        assert "Your submission was processed" in result
    
    def test_multiple_event_types(self, event_aggregator, sample_events):
        """Test aggregation groups events by type correctly"""
        user_events = [event for event in sample_events if event.user_id == "user_123"]
        
        result = event_aggregator.aggregate_events("user_123", user_events, AggregationMethod.PLAIN)
        
        # Should have separate sections for NOTIFICATION and ALERT
        assert "NOTIFICATION (1 events):" in result
        assert "ALERT (1 events):" in result
    
    def test_aggregation_includes_metadata(self, event_aggregator, sample_events):
        """Test that aggregation includes event metadata"""
        user_events = [sample_events[0]]  # Event with metadata
        
        result = event_aggregator.aggregate_events("user_123", user_events, AggregationMethod.HTML)
        
        # HTML should escape and include metadata
        assert "arxiv-submission" in result
        
        result = event_aggregator.aggregate_events("user_123", user_events, AggregationMethod.MIME)
        
        # MIME should include metadata
        assert "source" in result