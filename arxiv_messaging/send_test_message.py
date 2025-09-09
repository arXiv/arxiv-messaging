#!/usr/bin/env python3
"""
Send a test message to Pub/Sub for the messaging service
"""

import argparse
import os
import sys
import structlog
from . import send_notification
from .event_type import EventType

def setup_logging():
    """Configure structured logging"""
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

def send_test_message(project_id: str, topic_name: str, user_id = None, email_to: str = None, 
                     subject: str = "test", message: str = "test message", 
                     event_type: str = "NOTIFICATION", sender: str = "no-reply@arxiv.org"):
    """
    Send a test message to Pub/Sub topic using the send_notification function
    
    Args:
        project_id: GCP project ID
        topic_name: Pub/Sub topic name
        user_id: Target user ID(s) - string or list of strings (for registered users)
        email_to: Direct email address (for email gateway mode)
        subject: Message subject
        message: Message content
        event_type: Event type (NOTIFICATION, ALERT, etc.)
        sender: Sender email address
    """
    logger = structlog.get_logger(__name__)
    
    try:
        # Use the send_notification function with test metadata
        message_id = send_notification(
            user_id=user_id,
            email_to=email_to,
            subject=subject,
            message=message,
            sender=sender,
            event_type=event_type,
            metadata={"source": "test-script", "test": True},
            project_id=project_id,
            topic_name=topic_name,
            logger=logger
        )
        
        print(f"✅ Test message sent successfully!")
        print(f"   Message ID: {message_id}")
        if user_id:
            if isinstance(user_id, list):
                print(f"   Users: {', '.join(user_id)} ({len(user_id)} total)")
            else:
                print(f"   User: {user_id}")
        if email_to:
            print(f"   Email: {email_to}")
        print(f"   Subject: {subject}")
        print(f"   Topic: {topic_name}")
        
        return message_id
        
    except Exception as e:
        print(f"❌ Failed to send test message: {e}")
        raise

def main():
    setup_logging()
    
    parser = argparse.ArgumentParser(description='Send test message to Pub/Sub')
    parser.add_argument('--project-id', 
                       default=os.getenv('GCP_PROJECT_ID', 'arxiv-development'),
                       help='GCP project ID (default: arxiv-development)')
    parser.add_argument('--topic', 
                       default='notification-events',
                       help='Pub/Sub topic name (default: notification-events)')
    parser.add_argument('--user-id', 
                       help='Target user ID(s) - single user or comma-separated list (for registered users)')
    parser.add_argument('--email-to', 
                       help='Direct email address (for email gateway mode)')
    parser.add_argument('--subject', 
                       default='test',
                       help='Message subject (default: test)')
    parser.add_argument('--message', 
                       default='test message',
                       help='Message content (default: test message)')
    parser.add_argument('--event-type', 
                       default='NOTIFICATION',
                       choices=[et.value for et in EventType],
                       help='Event type (default: NOTIFICATION)')
    parser.add_argument('--sender', 
                       default='no-reply@arxiv.org',
                       help='Sender email address (default: no-reply@arxiv.org)')
    
    args = parser.parse_args()
    
    # Validate that either user_id or email_to is provided
    if not args.user_id and not args.email_to:
        # Default to devnull for backward compatibility
        args.user_id = 'devnull'
    
    # Parse user_id as comma-separated list if provided
    user_id = None
    if args.user_id:
        if ',' in args.user_id:
            user_id = [u.strip() for u in args.user_id.split(',')]
        else:
            user_id = args.user_id
    
    try:
        send_test_message(
            project_id=args.project_id,
            topic_name=args.topic,
            user_id=user_id,
            email_to=args.email_to,
            subject=args.subject,
            message=args.message,
            event_type=args.event_type,
            sender=args.sender
        )
    except Exception as e:
        sys.exit(1)

if __name__ == "__main__":
    main()