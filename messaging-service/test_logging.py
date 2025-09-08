#!/usr/bin/env python3
"""
Test script to verify JSON logging configuration
"""

import structlog
import logging

# Configure structured JSON logging (same as in main.py)
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logging.basicConfig(
    format="%(message)s",
    stream=None,
    level=logging.INFO,
)

def test_json_logging():
    """Test structured JSON logging"""
    logger = structlog.get_logger(__name__)
    
    # Test basic info log
    logger.info("Testing JSON logging configuration")
    
    # Test structured log with fields
    logger.info("Event processed successfully",
               event_id="test-123",
               user_id="user-456", 
               event_type="notification",
               sender="test@example.com")
    
    # Test warning log
    logger.warning("User preference not found",
                  user_id="unknown-user",
                  event_id="test-789")
    
    # Test error log with exception simulation
    try:
        raise ValueError("Simulated error for testing")
    except Exception as e:
        logger.error("Processing failed",
                    error=str(e),
                    user_id="test-user",
                    event_type="test")
    
    print("\n✅ JSON logging test completed. Check the structured JSON output above.")

if __name__ == "__main__":
    test_json_logging()