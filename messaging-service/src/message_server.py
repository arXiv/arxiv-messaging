import json
import logging
from datetime import datetime, timedelta
from enum import Enum
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import html
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from abc import ABC, abstractmethod
import threading
import time
from google.cloud import pubsub_v1
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
import schedule
import os
import structlog
import httpx
from .email_sender import send_email
from arxiv_messaging import EventType, DeliveryMethod, AggregationFrequency, AggregationMethod, DeliveryErrorStrategy, Subscription, UserPreference, Event

# Configure structured JSON logging
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

# Configure standard library logging to work with structlog
logging.basicConfig(
    format="%(message)s",
    stream=None,
    level=logging.INFO,
)

logger = structlog.get_logger(__name__)


@dataclass
class AggregatedEvent:
    user_id: str
    events: List[Event]
    aggregation_period: str
    created_at: datetime

# Abstract Delivery Interface
class DeliveryProvider(ABC):
    @abstractmethod
    def send(self, user_preference: UserPreference, content: str, subject: str = None, sender: str = None, correlation_id: str = None) -> bool:
        pass

class EmailDeliveryProvider(DeliveryProvider):
    def __init__(self):
        # Email configuration from environment variables
        self.smtp_server = os.environ.get('SMTP_SERVER', 'smtp-relay.gmail.com')
        self.smtp_port = int(os.environ.get('SMTP_PORT', '465'))
        self.smtp_user = os.environ.get('SMTP_USER', 'smtp-relay@arxiv.org')
        self.smtp_pass = os.environ.get('SMTP_PASSWORD', '')
        self.use_ssl = os.environ.get('SMTP_USE_SSL', 'true').lower() == 'true'
        self.default_sender = os.environ.get('DEFAULT_EMAIL_SENDER', 'arxiv-messaging@arxiv.org')

    def send(self, user_preference: UserPreference, content: str, subject: str = None, sender: str = None, correlation_id: str = None) -> bool:
        """Send email using SMTP"""
        if not user_preference.email_address:
            logger.error("Email address not configured for user",
                        user_id=user_preference.user_id,
                        subscription_id=getattr(user_preference, 'subscription_id', 'unknown'),
                        correlation_id=correlation_id)
            return False

        # Use provided sender or default
        email_sender = sender or self.default_sender
        email_subject = subject or "Notification"

        logger.info("Email delivery initiated", 
                   recipient=user_preference.email_address,
                   subject=email_subject,
                   sender=email_sender,
                   content_preview=content[:100],
                   delivery_method="email",
                   smtp_server=self.smtp_server,
                   smtp_port=self.smtp_port,
                   use_ssl=self.use_ssl,
                   user_id=user_preference.user_id,
                   subscription_id=getattr(user_preference, 'subscription_id', 'unknown'),
                   correlation_id=correlation_id)

        # Send email using the send_email function
        success = send_email(
            smtp_server=self.smtp_server,
            smtp_port=self.smtp_port,
            smtp_user=self.smtp_user,
            smtp_pass=self.smtp_pass,
            recipient=user_preference.email_address,
            sender=email_sender,
            subject=email_subject,
            body=content,
            use_ssl=self.use_ssl,
            logger=logger,
            correlation_id=correlation_id,
            subscription_id=getattr(user_preference, 'subscription_id', 'unknown')
        )

        if success:
            logger.info("Email delivered successfully",
                       user_id=user_preference.user_id,
                       recipient=user_preference.email_address,
                       subject=email_subject,
                       subscription_id=getattr(user_preference, 'subscription_id', 'unknown'),
                       correlation_id=correlation_id)
        else:
            logger.error("Email delivery failed",
                        user_id=user_preference.user_id,
                        recipient=user_preference.email_address,
                        sender=email_sender,
                        subject=email_subject,
                        smtp_server=self.smtp_server,
                        smtp_user=self.smtp_user,
                        subscription_id=getattr(user_preference, 'subscription_id', 'unknown'),
                        correlation_id=correlation_id)

        return success

class SlackDeliveryProvider(DeliveryProvider):
    def __init__(self):
        self.timeout = 30  # HTTP request timeout in seconds


    def send(self, user_preference: UserPreference, content: str, subject: str = None, sender: str = None, correlation_id: str = None) -> bool:
        """Send message to Slack via webhook"""
        if not user_preference.slack_webhook_url:
            logger.error("Slack webhook URL not configured for user",
                        user_id=user_preference.user_id,
                        subscription_id=getattr(user_preference, 'subscription_id', 'unknown'),
                        correlation_id=correlation_id)
            return False

        logger.info("Slack delivery initiated",
                   webhook_url=user_preference.slack_webhook_url[:50] + "...",
                   subject=subject,
                   sender=sender,
                   content_preview=content[:100],
                   delivery_method="slack",
                   user_id=user_preference.user_id,
                   subscription_id=getattr(user_preference, 'subscription_id', 'unknown'),
                   correlation_id=correlation_id)

        # Create webhook payload with subject and message
        payload = {
            "subject": subject or "Notification",
            "message": content,
            "sender": sender,
        }

        # Use synchronous httpx client for compatibility
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    user_preference.slack_webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                response.raise_for_status()
                logger.info("Slack webhook delivered successfully",
                           status_code=response.status_code,
                           user_id=user_preference.user_id,
                           webhook_url=user_preference.slack_webhook_url[:50] + "...",
                           subscription_id=getattr(user_preference, 'subscription_id', 'unknown'),
                           correlation_id=correlation_id)
                return True
        except httpx.HTTPError as e:
            logger.error("Slack webhook delivery failed",
                        error=str(e),
                        user_id=user_preference.user_id,
                        webhook_url=user_preference.slack_webhook_url[:50] + "...",
                        sender=sender,
                        subject=subject,
                        subscription_id=getattr(user_preference, 'subscription_id', 'unknown'),
                        correlation_id=correlation_id)
            return False
        except Exception as e:
            logger.error("Unexpected error in Slack delivery",
                        error=str(e),
                        user_id=user_preference.user_id,
                        sender=sender,
                        subject=subject,
                        subscription_id=getattr(user_preference, 'subscription_id', 'unknown'),
                        correlation_id=correlation_id)
            return False

class DeliveryService:
    def __init__(self):
        self.providers = {
            DeliveryMethod.EMAIL: EmailDeliveryProvider(),
            DeliveryMethod.SLACK: SlackDeliveryProvider()
        }
    
    def deliver(self, user_preference: UserPreference, content: str, subject: str = None, sender: str = None, correlation_id: str = None) -> bool:
        provider = self.providers.get(user_preference.delivery_method)
        if not provider:
            logger.error("No delivery provider found", 
                        delivery_method=user_preference.delivery_method.value,
                        user_id=user_preference.user_id,
                        subscription_id=getattr(user_preference, 'subscription_id', 'unknown'),
                        correlation_id=correlation_id)
            return False
        
        try:
            return provider.send(user_preference, content, subject, sender, correlation_id=correlation_id)
        except Exception as e:
            logger.error("Delivery failed", 
                        error=str(e),
                        delivery_method=user_preference.delivery_method.value,
                        user_id=user_preference.user_id,
                        subscription_id=getattr(user_preference, 'subscription_id', 'unknown'),
                        correlation_id=correlation_id)
            return False

class EventStore:
    """Handles event storage and retrieval using Firestore"""
    
    def __init__(self, project_id: Optional[str] = None, database_id: str = "messaging"):
        # Initialize Firestore client
        if not project_id:
            project_id = os.getenv('GCP_PROJECT_ID')
        
        if not project_id:
            raise ValueError("GCP_PROJECT_ID environment variable must be set or project_id must be provided")
            
        # Use specific database if not default
        if database_id != "(default)":
            from google.cloud.firestore import Client
            self.db = Client(project=project_id, database=database_id)
        else:
            self.db = firestore.Client(project=project_id)
            
        self.database_id = database_id
        self.events_collection = 'events'
        self.subscriptions_collection = 'subscriptions'
        # Keep old collection name for backward compatibility during migration
        self.preferences_collection = 'user_preferences'
    
    def store_event(self, event: Event):
        """Store an individual event"""
        try:
            # Convert event to dict for Firestore storage
            event_dict = asdict(event)
            # Convert datetime to timestamp for Firestore
            event_dict['timestamp'] = event.timestamp
            # Convert EventType enum to string for Firestore storage
            event_dict['event_type'] = event.event_type.value
            
            # Store in Firestore
            doc_ref = self.db.collection(self.events_collection).document(event.event_id)
            doc_ref.set(event_dict)
            
            logger.info("Event stored successfully",
                       event_id=event.event_id,
                       user_id=event.user_id,
                       event_type=event.event_type.value)
        except Exception as e:
            logger.error("Failed to store event",
                        event_id=event.event_id,
                        user_id=event.user_id,
                        error=str(e))
            raise
    
    def get_user_events(self, user_id: str, since: datetime = None) -> List[Event]:
        """Retrieve events for a user since a specific time"""
        try:
            # Query events for the user
            query = self.db.collection(self.events_collection).where(filter=FieldFilter('user_id', '==', user_id))
            
            # Add time filter if specified
            if since:
                query = query.where(filter=FieldFilter('timestamp', '>=', since))
            
            # Order by timestamp
            query = query.order_by('timestamp')
            
            # Execute query and convert to Event objects
            events = []
            for doc in query.stream():
                data = doc.to_dict()
                # Convert string event_type back to EventType enum
                event_type_str = data['event_type']
                try:
                    event_type_enum = EventType(event_type_str)
                except ValueError:
                    logger.warning("Unknown event_type from Firestore, defaulting to NOTIFICATION", 
                                  event_type=event_type_str)
                    event_type_enum = EventType.NOTIFICATION
                    
                event = Event(
                    event_id=data['event_id'],
                    user_id=data['user_id'],
                    event_type=event_type_enum,
                    message=data['message'],
                    sender=data.get('sender', ''),
                    subject=data.get('subject', ''),
                    timestamp=data['timestamp'],
                    metadata=data.get('metadata', {})
                )
                events.append(event)
            
            return events
            
        except Exception as e:
            logger.error("Failed to get events for user",
                        user_id=user_id,
                        error=str(e))
            return []
    
    def clear_user_events(self, user_id: str, before: datetime):
        """Clear events for a user before a specific time"""
        try:
            # Query events to delete
            query = (self.db.collection(self.events_collection)
                    .where(filter=FieldFilter('user_id', '==', user_id))
                    .where(filter=FieldFilter('timestamp', '<', before)))
            
            # Delete events in batches
            batch = self.db.batch()
            docs = query.stream()
            count = 0
            
            for doc in docs:
                batch.delete(doc.reference)
                count += 1
                
                # Commit batch every 500 operations (Firestore limit)
                if count % 500 == 0:
                    batch.commit()
                    batch = self.db.batch()
            
            # Commit remaining operations
            if count % 500 != 0:
                batch.commit()
            
            logger.info("Events cleared for user",
                       user_id=user_id,
                       events_cleared=count,
                       before_timestamp=before.isoformat())
            
        except Exception as e:
            logger.error("Failed to clear events for user",
                        user_id=user_id,
                        error=str(e))
            raise
    
    def store_subscription(self, subscription: Subscription):
        """Store subscription"""
        try:
            # Convert subscription to dict for Firestore storage
            subscription_dict = asdict(subscription)
            # Convert enum values to strings
            subscription_dict['delivery_method'] = subscription.delivery_method.value
            subscription_dict['aggregation_frequency'] = subscription.aggregation_frequency.value
            subscription_dict['aggregation_method'] = subscription.aggregation_method.value
            subscription_dict['delivery_error_strategy'] = subscription.delivery_error_strategy.value
            
            # Store in Firestore using subscription_id as document ID
            doc_ref = self.db.collection(self.subscriptions_collection).document(subscription.subscription_id)
            doc_ref.set(subscription_dict)
            
            logger.info("Subscription stored",
                       subscription_id=subscription.subscription_id,
                       user_id=subscription.user_id,
                       delivery_method=subscription.delivery_method.value,
                       aggregation_frequency=subscription.aggregation_frequency.value,
                       enabled=subscription.enabled)
        except Exception as e:
            logger.error("Failed to store subscription",
                        subscription_id=subscription.subscription_id,
                        user_id=subscription.user_id,
                        error=str(e))
            raise

    # Backward compatibility method
    def store_user_preference(self, preference: UserPreference):
        """Store user preference (backward compatibility)"""
        # Generate subscription_id if not present
        if not hasattr(preference, 'subscription_id') or not preference.subscription_id:
            preference.subscription_id = f"{preference.user_id}-{preference.delivery_method.value}"
        return self.store_subscription(preference)
    
    def get_user_subscriptions(self, user_id: str) -> List[Subscription]:
        """Retrieve all subscriptions for a user"""
        try:
            # Query subscriptions collection for this user
            query = self.db.collection(self.subscriptions_collection).where(filter=FieldFilter('user_id', '==', user_id)).where(filter=FieldFilter('enabled', '==', True))
            docs = query.stream()
            
            subscriptions = []
            for doc in docs:
                data = doc.to_dict()
                subscription = Subscription(
                    subscription_id=data.get('subscription_id', doc.id),
                    user_id=data['user_id'],
                    delivery_method=DeliveryMethod(data['delivery_method']),
                    aggregation_frequency=AggregationFrequency(data['aggregation_frequency']),
                    aggregation_method=AggregationMethod(data.get('aggregation_method', 'plain')),
                    delivery_error_strategy=DeliveryErrorStrategy(data.get('delivery_error_strategy', 'retry')),
                    delivery_time=data.get('delivery_time', '09:00'),
                    timezone=data.get('timezone', 'UTC'),
                    email_address=data.get('email_address'),
                        slack_webhook_url=data.get('slack_webhook_url'),
                    enabled=data.get('enabled', True)
                )
                subscriptions.append(subscription)
            
            return subscriptions
            
        except Exception as e:
            logger.error("Failed to get user subscriptions",
                        user_id=user_id,
                        error=str(e))
            return []

    # Backward compatibility method - returns first subscription
    def get_user_preference(self, user_id: str) -> Optional[UserPreference]:
        """Retrieve user preference (backward compatibility - returns first subscription)"""
        subscriptions = self.get_user_subscriptions(user_id)
        if subscriptions:
            return subscriptions[0]
        
        # Fallback to old collection for migration period
        try:
            doc_ref = self.db.collection(self.preferences_collection).document(user_id)
            doc = doc_ref.get()
            
            if not doc.exists:
                return None
            
            data = doc.to_dict()
            # Convert old format to new subscription format
            preference = UserPreference(
                subscription_id=f"{user_id}-{data['delivery_method']}",
                user_id=data['user_id'],
                delivery_method=DeliveryMethod(data['delivery_method']),
                aggregation_frequency=AggregationFrequency(data['aggregation_frequency']),
                aggregation_method=AggregationMethod(data.get('aggregation_method', 'plain')),
                delivery_error_strategy=DeliveryErrorStrategy(data.get('delivery_error_strategy', 'retry')),
                delivery_time=data.get('delivery_time', '09:00'),
                timezone=data.get('timezone', 'UTC'),
                email_address=data.get('email_address'),
                slack_webhook_url=data.get('slack_webhook_url'),
                enabled=True
            )
            
            return preference
            
        except Exception as e:
            logger.error("Failed to get user preference from legacy collection",
                        user_id=user_id,
                        error=str(e))
            return None
    
    def get_all_preferences(self) -> List[UserPreference]:
        """Get all user preferences"""
        try:
            preferences = []
            docs = self.db.collection(self.preferences_collection).stream()
            
            for doc in docs:
                data = doc.to_dict()
                preference = UserPreference(
                    user_id=data['user_id'],
                    delivery_method=DeliveryMethod(data['delivery_method']),
                    aggregation_frequency=AggregationFrequency(data['aggregation_frequency']),
                    aggregation_method=AggregationMethod(data.get('aggregation_method', 'plain')),
                    delivery_error_strategy=DeliveryErrorStrategy(data.get('delivery_error_strategy', 'retry')),
                    delivery_time=data.get('delivery_time', '09:00'),
                    timezone=data.get('timezone', 'UTC'),
                    email_address=data.get('email_address'),
                        slack_webhook_url=data.get('slack_webhook_url')
                )
                preferences.append(preference)
            
            return preferences
            
        except Exception as e:
            logger.error("Failed to get all user preferences",
                        error=str(e))
            return []

    def get_undelivered_events(self, limit: Optional[int] = None) -> Dict[str, List[Event]]:
        """Get all undelivered events grouped by user_id"""
        try:
            query = self.db.collection(self.events_collection)
            if limit:
                query = query.limit(limit)
            
            docs = query.stream()
            events_by_user = {}
            
            for doc in docs:
                data = doc.to_dict()
                user_id = data['user_id']
                
                # Convert string back to EventType enum
                try:
                    event_type_str = data.get('event_type', 'NOTIFICATION')
                    event_type_enum = EventType(event_type_str)
                except ValueError:
                    logger.warning("Unknown event_type from Firestore, defaulting to NOTIFICATION", 
                                  event_type=event_type_str)
                    event_type_enum = EventType.NOTIFICATION
                    
                event = Event(
                    event_id=data['event_id'],
                    user_id=data['user_id'],
                    event_type=event_type_enum,
                    message=data['message'],
                    sender=data.get('sender', ''),
                    subject=data.get('subject', ''),
                    timestamp=data['timestamp'],
                    metadata=data.get('metadata', {})
                )
                
                if user_id not in events_by_user:
                    events_by_user[user_id] = []
                events_by_user[user_id].append(event)
            
            return events_by_user
            
        except Exception as e:
            logger.error("Failed to get undelivered events", error=str(e))
            return {}

    def get_events_for_user(self, user_id: str) -> List[Event]:
        """Get undelivered events for a specific user from Firestore"""
        try:
            logger.debug("Getting events for user", user_id=user_id)
            
            # Query undelivered events for the user
            events_ref = self.db.collection('events')
            query = events_ref.where('user_id', '==', user_id).where('delivered', '==', False)
            
            events = []
            docs = query.stream()
            
            for doc in docs:
                event_data = doc.to_dict()
                
                # Convert timestamp
                timestamp = event_data.get('timestamp')
                if hasattr(timestamp, 'timestamp'):
                    event_data['timestamp'] = datetime.fromtimestamp(timestamp.timestamp())
                
                # Create Event object
                event = Event(
                    event_id=event_data['event_id'],
                    user_id=event_data['user_id'],
                    event_type=EventType(event_data['event_type']),
                    message=event_data['message'],
                    sender=event_data['sender'],
                    subject=event_data['subject'],
                    timestamp=event_data['timestamp'],
                    metadata=event_data.get('metadata', {})
                )
                events.append(event)
            
            logger.debug("Retrieved events for user", user_id=user_id, event_count=len(events))
            return events
            
        except Exception as e:
            logger.error("Failed to get events for user", user_id=user_id, error=str(e))
            return []

    def get_undelivered_events_by_user(self, user_id: str) -> List[Event]:
        """Get undelivered events for a specific user"""
        return self.get_events_for_user(user_id)

    def get_undelivered_stats(self) -> Dict[str, Any]:
        """Get statistics about undelivered messages"""
        try:
            undelivered_events = self.get_undelivered_events()
            
            stats = {
                'total_users_with_undelivered': len(undelivered_events),
                'total_undelivered_events': sum(len(events) for events in undelivered_events.values()),
                'users_with_counts': {user_id: len(events) for user_id, events in undelivered_events.items()},
                'events_by_type': {}
            }
            
            # Count events by type
            for events in undelivered_events.values():
                for event in events:
                    event_type = event.event_type.value
                    if event_type not in stats['events_by_type']:
                        stats['events_by_type'][event_type] = 0
                    stats['events_by_type'][event_type] += 1
            
            return stats
            
        except Exception as e:
            logger.error("Failed to get undelivered stats", error=str(e))
            return {}

    def flush_undelivered_messages(self, delivery_service: 'DeliveryService', aggregator: 'EventAggregator', user_id: str = None, force_delivery: bool = False) -> Dict[str, Any]:
        """Flush undelivered messages by delivering them with appropriate aggregation
        
        Args:
            delivery_service: DeliveryService instance to use for sending
            aggregator: EventAggregator instance for formatting messages
            user_id: Optional specific user ID to flush messages for (None = all users)
            force_delivery: If True, deliver regardless of aggregation preferences
            
        Returns:
            Dict with flush results and statistics
        """
        try:
            flush_results = {
                'users_processed': 0,
                'messages_delivered': 0,
                'messages_failed': 0,
                'events_cleared': 0,
                'errors': []
            }
            
            # Get undelivered events
            if user_id:
                undelivered_events = {user_id: self.get_undelivered_events_by_user(user_id)}
                undelivered_events = {k: v for k, v in undelivered_events.items() if v}
            else:
                undelivered_events = self.get_undelivered_events()
            
            logger.info("Starting flush of undelivered messages",
                       total_users=len(undelivered_events),
                       total_events=sum(len(events) for events in undelivered_events.values()),
                       target_user=user_id,
                       force_delivery=force_delivery)
            
            # Process each user's undelivered events
            for current_user_id, events in undelivered_events.items():
                try:
                    flush_results['users_processed'] += 1
                    
                    # Get user subscriptions
                    subscriptions = self.get_user_subscriptions(current_user_id)
                    if not subscriptions:
                        logger.warning("No subscriptions found for user",
                                     user_id=current_user_id,
                                     undelivered_events=len(events))
                        continue
                    
                    # Process each subscription for this user
                    for subscription in subscriptions:
                        if not subscription.enabled:
                            continue
                            
                        try:
                            # Aggregate events according to subscription preferences
                            content = aggregator.aggregate_events(
                                current_user_id, 
                                events, 
                                subscription.aggregation_method
                            )
                            
                            if not content:
                                continue
                            
                            # Create subject and sender for flush message
                            subject = f"Undelivered Messages Summary for {current_user_id}"
                            sender = "arxiv-messaging-flush@arxiv.org"
                            
                            # Attempt delivery
                            correlation_id = f"flush-{current_user_id}-{int(datetime.now().timestamp())}"
                            
                            logger.info("Attempting to flush undelivered messages",
                                       user_id=current_user_id,
                                       subscription_id=subscription.subscription_id,
                                       event_count=len(events),
                                       delivery_method=subscription.delivery_method.value,
                                       aggregation_method=subscription.aggregation_method.value,
                                       correlation_id=correlation_id)
                            
                            success = delivery_service.deliver(
                                subscription, 
                                content, 
                                subject=subject,
                                sender=sender,
                                correlation_id=correlation_id
                            )
                            
                            if success:
                                flush_results['messages_delivered'] += 1
                                logger.info("Undelivered messages flushed successfully",
                                           user_id=current_user_id,
                                           subscription_id=subscription.subscription_id,
                                           events_delivered=len(events),
                                           correlation_id=correlation_id)
                            else:
                                flush_results['messages_failed'] += 1
                                error_msg = f"Failed to deliver flush message for user {current_user_id}, subscription {subscription.subscription_id}"
                                flush_results['errors'].append(error_msg)
                                logger.error("Failed to flush undelivered messages",
                                           user_id=current_user_id,
                                           subscription_id=subscription.subscription_id,
                                           correlation_id=correlation_id)
                                
                        except Exception as e:
                            flush_results['messages_failed'] += 1
                            error_msg = f"Error processing subscription {subscription.subscription_id} for user {current_user_id}: {str(e)}"
                            flush_results['errors'].append(error_msg)
                            logger.error("Error during flush delivery",
                                       user_id=current_user_id,
                                       subscription_id=subscription.subscription_id,
                                       error=str(e))
                    
                    # Clear events after successful delivery (or if force_delivery is True)
                    if flush_results['messages_delivered'] > 0 or force_delivery:
                        # Clear all events for this user 
                        self.clear_user_events(current_user_id, datetime.now())
                        flush_results['events_cleared'] += len(events)
                        logger.info("Cleared undelivered events after flush",
                                   user_id=current_user_id,
                                   events_cleared=len(events))
                        
                except Exception as e:
                    error_msg = f"Error processing user {current_user_id}: {str(e)}"
                    flush_results['errors'].append(error_msg)
                    logger.error("Error processing user during flush",
                               user_id=current_user_id,
                               error=str(e))
            
            logger.info("Completed flush of undelivered messages",
                       **flush_results)
            
            return flush_results
            
        except Exception as e:
            logger.error("Failed to flush undelivered messages", error=str(e))
            return {
                'users_processed': 0,
                'messages_delivered': 0,
                'messages_failed': 0,
                'events_cleared': 0,
                'errors': [f"Flush operation failed: {str(e)}"]
            }

    def delete_event_by_id(self, event_id: str) -> bool:
        """Delete a specific event by its ID"""
        try:
            doc_ref = self.db.collection(self.events_collection).document(event_id)
            doc = doc_ref.get()
            
            if not doc.exists:
                logger.warning("Event not found for deletion", event_id=event_id)
                return False
            
            doc_ref.delete()
            logger.info("Event deleted successfully", event_id=event_id)
            return True
            
        except Exception as e:
            logger.error("Failed to delete event", event_id=event_id, error=str(e))
            return False

    def delete_events_by_ids(self, event_ids: List[str]) -> Dict[str, Any]:
        """Delete multiple events by their IDs"""
        try:
            deleted_count = 0
            failed_ids = []
            
            # Delete in batches for efficiency
            batch = self.db.batch()
            batch_size = 0
            
            for event_id in event_ids:
                try:
                    doc_ref = self.db.collection(self.events_collection).document(event_id)
                    batch.delete(doc_ref)
                    batch_size += 1
                    
                    # Commit batch every 500 operations (Firestore limit)
                    if batch_size >= 500:
                        batch.commit()
                        deleted_count += batch_size
                        batch = self.db.batch()
                        batch_size = 0
                        
                except Exception as e:
                    failed_ids.append(event_id)
                    logger.error("Failed to add event to delete batch", 
                               event_id=event_id, error=str(e))
            
            # Commit remaining operations
            if batch_size > 0:
                batch.commit()
                deleted_count += batch_size
            
            logger.info("Bulk event deletion completed",
                       total_requested=len(event_ids),
                       deleted=deleted_count,
                       failed=len(failed_ids))
            
            return {
                'deleted_count': deleted_count,
                'failed_ids': failed_ids,
                'total_requested': len(event_ids)
            }
            
        except Exception as e:
            logger.error("Failed bulk event deletion", error=str(e))
            return {
                'deleted_count': 0,
                'failed_ids': event_ids,
                'total_requested': len(event_ids)
            }

    def get_all_users_with_subscriptions(self) -> List[str]:
        """Get list of all user IDs that have subscriptions"""
        try:
            docs = self.db.collection(self.subscriptions_collection).stream()
            user_ids = set()
            
            for doc in docs:
                data = doc.to_dict()
                if 'user_id' in data:
                    user_ids.add(data['user_id'])
            
            return list(user_ids)
            
        except Exception as e:
            logger.error("Failed to get users with subscriptions", error=str(e))
            return []

    def delete_subscription(self, subscription_id: str) -> bool:
        """Delete a subscription by its ID"""
        try:
            doc_ref = self.db.collection(self.subscriptions_collection).document(subscription_id)
            doc = doc_ref.get()
            
            if not doc.exists:
                logger.warning("Subscription not found for deletion", subscription_id=subscription_id)
                return False
            
            doc_ref.delete()
            logger.info("Subscription deleted successfully", subscription_id=subscription_id)
            return True
            
        except Exception as e:
            logger.error("Failed to delete subscription", subscription_id=subscription_id, error=str(e))
            return False

class EventAggregator:
    """Handles event aggregation logic"""
    
    def __init__(self, event_store: EventStore):
        self.event_store = event_store
    
    def aggregate_events(self, user_id: str, events: List[Event], method: AggregationMethod = AggregationMethod.PLAIN) -> str:
        """Aggregate events into a formatted message"""
        if not events:
            return ""
        
        if method == AggregationMethod.PLAIN:
            return self._aggregate_plain(user_id, events)
        elif method == AggregationMethod.MIME:
            return self._aggregate_mime(user_id, events)
        elif method == AggregationMethod.HTML:
            return self._aggregate_html(user_id, events)
        else:
            return self._aggregate_plain(user_id, events)
    
    def _aggregate_plain(self, user_id: str, events: List[Event]) -> str:
        """Aggregate events into plain text format (current method)"""
        # Group events by type
        events_by_type = {}
        for event in events:
            if event.event_type not in events_by_type:
                events_by_type[event.event_type] = []
            events_by_type[event.event_type].append(event)
        
        # Build aggregated message
        message_parts = [
            f"Event Summary for User {user_id}",
            f"Period: {events[0].timestamp.strftime('%Y-%m-%d')} to {events[-1].timestamp.strftime('%Y-%m-%d')}",
            f"Total Events: {len(events)}",
            "-" * 50
        ]
        
        for event_type, type_events in events_by_type.items():
            message_parts.extend([
                f"\n{event_type.value.upper()} ({len(type_events)} events):",
                "-" * 30
            ])
            
            for event in type_events[-5:]:  # Show last 5 events of each type
                message_parts.append(f"• {event.timestamp.strftime('%H:%M')} - {event.message}")
            
            if len(type_events) > 5:
                message_parts.append(f"... and {len(type_events) - 5} more")
        
        return "\n".join(message_parts)
    
    def _aggregate_mime(self, user_id: str, events: List[Event]) -> str:
        """Aggregate events into MIME multipart format"""
        # Create multipart message
        msg = MIMEMultipart()
        msg['Subject'] = f"Event Summary for User {user_id}"
        msg['From'] = "arXiv Messaging System"
        msg['To'] = user_id
        
        # Add summary as first part
        summary = MIMEText(
            f"Event Summary for User {user_id}\n"
            f"Period: {events[0].timestamp.strftime('%Y-%m-%d')} to {events[-1].timestamp.strftime('%Y-%m-%d')}\n"
            f"Total Events: {len(events)}\n"
            f"{'='*50}\n\n"
        )
        summary.add_header('Content-Disposition', 'inline', filename='summary.txt')
        msg.attach(summary)
        
        # Group events by type
        events_by_type = {}
        for event in events:
            if event.event_type not in events_by_type:
                events_by_type[event.event_type] = []
            events_by_type[event.event_type].append(event)
        
        # Create separate MIME part for each event type
        for event_type, type_events in events_by_type.items():
            event_content = [
                f"{event_type.value.upper()} Events ({len(type_events)} total)",
                "="*40,
                ""
            ]
            
            for event in type_events:
                event_content.extend([
                    f"Event ID: {event.event_id}",
                    f"Timestamp: {event.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
                    f"Sender: {event.sender}",
                    f"Subject: {event.subject}",
                    f"Message: {event.message}",
                    f"Metadata: {event.metadata}",
                    "-" * 30,
                    ""
                ])
            
            part = MIMEText("\n".join(event_content))
            part.add_header('Content-Disposition', 'inline', filename=f'{event_type.value}_events.txt')
            msg.attach(part)
        
        return msg.as_string()
    
    def _aggregate_html(self, user_id: str, events: List[Event]) -> str:
        """Aggregate events into HTML table format"""
        # Group events by type
        events_by_type = {}
        for event in events:
            if event.event_type not in events_by_type:
                events_by_type[event.event_type] = []
            events_by_type[event.event_type].append(event)
        
        # Build HTML
        html_parts = [
            "<!DOCTYPE html>",
            "<html><head>",
            "<title>Event Summary</title>",
            "<style>",
            "body { font-family: Arial, sans-serif; margin: 20px; }",
            "h1 { color: #333; border-bottom: 2px solid #ddd; }",
            "h2 { color: #666; margin-top: 30px; }",
            ".summary { background: #f5f5f5; padding: 15px; border-radius: 5px; margin-bottom: 20px; }",
            "table { border-collapse: collapse; width: 100%; margin-bottom: 30px; }",
            "th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }",
            "th { background-color: #f2f2f2; font-weight: bold; }",
            "tr:nth-child(even) { background-color: #f9f9f9; }",
            ".timestamp { white-space: nowrap; }",
            ".message { max-width: 300px; word-wrap: break-word; }",
            "</style>",
            "</head><body>",
            f"<h1>Event Summary for User {html.escape(user_id)}</h1>",
            "<div class='summary'>",
            f"<strong>Period:</strong> {events[0].timestamp.strftime('%Y-%m-%d')} to {events[-1].timestamp.strftime('%Y-%m-%d')}<br>",
            f"<strong>Total Events:</strong> {len(events)}",
            "</div>"
        ]
        
        # Create table for each event type
        for event_type, type_events in events_by_type.items():
            html_parts.extend([
                f"<h2>{html.escape(event_type.value.upper())} Events ({len(type_events)} total)</h2>",
                "<table>",
                "<tr>",
                "<th>Timestamp</th>",
                "<th>Event ID</th>",
                "<th>Sender</th>",
                "<th>Subject</th>",
                "<th>Message</th>",
                "<th>Metadata</th>",
                "</tr>"
            ])
            
            for event in type_events:
                html_parts.extend([
                    "<tr>",
                    f"<td class='timestamp'>{html.escape(event.timestamp.strftime('%Y-%m-%d %H:%M:%S'))}</td>",
                    f"<td>{html.escape(event.event_id)}</td>",
                    f"<td>{html.escape(event.sender)}</td>",
                    f"<td>{html.escape(event.subject)}</td>",
                    f"<td class='message'>{html.escape(event.message)}</td>",
                    f"<td>{html.escape(str(event.metadata))}</td>",
                    "</tr>"
                ])
            
            html_parts.append("</table>")
        
        html_parts.extend([
            "</body></html>"
        ])
        
        return "\n".join(html_parts)

class PubSubEventProcessor:
    """Handles GCP Pub/Sub event processing"""
    
    def __init__(self, project_id: str, subscription_name: str, event_store: EventStore, delivery_service: DeliveryService):
        self.project_id = project_id
        self.subscription_name = subscription_name
        self.event_store = event_store
        self.delivery_service = delivery_service
        self.subscriber = pubsub_v1.SubscriberClient()
        self.subscription_path = self.subscriber.subscription_path(project_id, subscription_name)
        self.aggregator = EventAggregator(event_store)
    
    def _safe_ack(self, message, event_id: str = None):
        """Safely acknowledge a message with error handling"""
        try:
            message.ack()
        except Exception as e:
            logger.error("Failed to acknowledge message - message may be redelivered",
                        event_id=event_id,
                        error=str(e),
                        error_type=type(e).__name__)
    
    def _safe_nack(self, message, event_id: str = None):
        """Safely nack a message with error handling"""
        try:
            message.nack()
        except Exception as e:
            logger.error("Failed to nack message - message delivery status unclear",
                        event_id=event_id,
                        error=str(e),
                        error_type=type(e).__name__)

    def process_message(self, message):
        """Process a single Pub/Sub message"""
        event_id = None
        try:
            # Parse the message
            data = json.loads(message.data.decode('utf-8'))
            event_id = data.get('event_id', 'unknown')
            
            # Check if this is an email gateway message (has email_to instead of user_id)
            email_to = data.get('email_to')
            user_id_raw = data.get('user_id')
            
            if email_to and not user_id_raw:
                # Handle as email gateway - immediate email delivery
                import uuid
                correlation_id = str(uuid.uuid4())[:8]
                logger.info("Processing email gateway message",
                           email_to=email_to,
                           subject=data.get('subject', ''),
                           sender=data.get('sender', ''),
                           event_id=event_id,
                           correlation_id=correlation_id)
                
                # Create temporary user preference for immediate email delivery
                temp_preference = UserPreference(
                    subscription_id=f"gateway-{email_to}",
                    user_id=f"gateway-{email_to}",
                    delivery_method=DeliveryMethod.EMAIL,
                    aggregation_frequency=AggregationFrequency.IMMEDIATE,
                    aggregation_method=AggregationMethod.PLAIN,
                    email_address=email_to,
                    timezone="UTC"
                )
                
                # Send email immediately without storing the event
                self.delivery_service.deliver(
                    temp_preference, 
                    data.get('message', ''), 
                    data.get('subject', ''), 
                    data.get('sender', 'no-reply@arxiv.org'),
                    correlation_id=correlation_id
                )
                
                self._safe_ack(message, event_id)
                return
            
            # Handle user_id as either string or list
            if not user_id_raw:
                logger.error("Message missing both user_id and email_to - unable to deliver, discarding message",
                           message_data=data,
                           event_id=event_id)
                self._safe_ack(message, event_id)  # Acknowledge to prevent redelivery of undeliverable message
                return
            
            # Normalize user_id to list
            if isinstance(user_id_raw, str):
                user_ids = [user_id_raw]
            elif isinstance(user_id_raw, list):
                user_ids = user_id_raw
            else:
                logger.error("Invalid user_id format - must be string or list",
                           user_id=user_id_raw,
                           event_id=event_id)
                self._safe_ack(message, event_id)
                return
            
            if not user_ids:
                logger.error("Empty user_id list - unable to deliver, discarding message",
                           event_id=event_id)
                self._safe_ack(message, event_id)
                return
            
            # Generate correlation ID for multi-user processing
            import uuid
            correlation_id = str(uuid.uuid4())[:8]
            
            logger.info("Processing Pub/Sub event for multiple users",
                       event_id=event_id,
                       user_count=len(user_ids),
                       user_ids=user_ids[:5],  # Log first 5 users to avoid spam
                       correlation_id=correlation_id)
            
            # Process each user separately
            processed_users = []
            failed_users = []
            failed_subscriptions = []
            
            for user_id in user_ids:
                try:
                    self._process_single_user_event(data, user_id, event_id)
                    processed_users.append(user_id)
                except Exception as e:
                    # Try to get subscription info for this user if possible
                    try:
                        user_subscriptions = self.event_store.get_user_subscriptions(user_id)
                        subscription_ids = [sub.subscription_id for sub in user_subscriptions] if user_subscriptions else ["unknown"]
                        failed_subscriptions.extend(subscription_ids)
                    except:
                        subscription_ids = ["unknown"]
                        failed_subscriptions.append("unknown")
                    
                    logger.error("Failed to process event for user",
                               user_id=user_id,
                               event_id=event_id,
                               error=str(e),
                               correlation_id=correlation_id,
                               subscription_ids=subscription_ids)
                    failed_users.append(user_id)
            
            logger.info("Multi-user event processing completed",
                       event_id=event_id,
                       total_users=len(user_ids),
                       processed=len(processed_users),
                       failed=len(failed_users),
                       correlation_id=correlation_id)
            
            # Only acknowledge if all users succeeded
            if failed_users:
                logger.error("Some users failed processing - will retry entire message",
                           event_id=event_id,
                           failed_users=failed_users,
                           failed_count=len(failed_users),
                           failed_subscriptions=failed_subscriptions,
                           correlation_id=correlation_id)
                self._safe_nack(message, event_id)
            else:
                self._safe_ack(message, event_id)
            
        except Exception as e:
            logger.error("Error processing Pub/Sub message - will retry",
                        event_id=event_id,
                        error=str(e),
                        error_type=type(e).__name__)
            self._safe_nack(message, event_id)
    
    def _process_single_user_event(self, data: dict, user_id: str, event_id: str):
        """Process event for a single user"""
        import uuid
        # Generate correlation ID for tracking this processing session
        correlation_id = str(uuid.uuid4())[:8]
        # Create Event object
        event_type_str = data.get('event_type', 'NOTIFICATION')
        # Convert string to EventType enum
        try:
            event_type_enum = EventType(event_type_str)
        except ValueError:
            logger.warning("Unknown event_type, defaulting to NOTIFICATION", 
                          event_type=event_type_str,
                          event_id=event_id,
                          user_id=user_id)
            event_type_enum = EventType.NOTIFICATION
        
        # Create unique event_id for each user to avoid conflicts
        user_event_id = f"{event_id}-{user_id}"
        
        event = Event(
            event_id=user_event_id,
            user_id=user_id,
            event_type=event_type_enum,
            message=data.get('message', ''),
            sender=data.get('sender', ''),
            subject=data.get('subject', ''),
            timestamp=datetime.fromisoformat(data.get('timestamp', datetime.now().isoformat())),
            metadata=data.get('metadata', {})
        )
        
        logger.info("Processing single user event",
                   event_id=event.event_id,
                   user_id=event.user_id,
                   event_type=event.event_type.value,
                   sender=event.sender,
                   correlation_id=correlation_id)
        
        # Get all subscriptions for this user
        user_subscriptions = self.event_store.get_user_subscriptions(event.user_id)
        if not user_subscriptions:
            logger.warning("No subscriptions found - skipping user",
                          user_id=event.user_id,
                          event_id=event.event_id,
                          correlation_id=correlation_id)
            return  # Skip this user but don't fail the whole message
        
        # Store the event (once per user, regardless of number of subscriptions)
        self.event_store.store_event(event)
        
        # Process each subscription for immediate delivery
        failed_subscriptions = []
        successful_subscriptions = []
        
        for subscription in user_subscriptions:
            if subscription.aggregation_frequency == AggregationFrequency.IMMEDIATE:
                logger.info("Processing immediate delivery for subscription",
                           subscription_id=subscription.subscription_id,
                           user_id=user_id,
                           delivery_method=subscription.delivery_method.value,
                           correlation_id=correlation_id)
                
                # For immediate delivery, send the raw message content without aggregation
                success = self.delivery_service.deliver(subscription, event.message, event.subject, event.sender, correlation_id=correlation_id)
                
                # Handle delivery failure based on subscription's strategy
                if not success:
                    if subscription.delivery_error_strategy == DeliveryErrorStrategy.RETRY:
                        logger.warning("Delivery failed - will retry based on subscription preference",
                                     subscription_id=subscription.subscription_id,
                                     user_id=user_id,
                                     event_id=event.event_id,
                                     strategy=subscription.delivery_error_strategy.value,
                                     correlation_id=correlation_id)
                        failed_subscriptions.append(subscription.subscription_id)
                    else:  # IGNORE strategy
                        logger.warning("Delivery failed - ignoring based on subscription preference",
                                     subscription_id=subscription.subscription_id,
                                     user_id=user_id,
                                     event_id=event.event_id,
                                     strategy=subscription.delivery_error_strategy.value,
                                     correlation_id=correlation_id)
                        successful_subscriptions.append(subscription.subscription_id)
                else:
                    successful_subscriptions.append(subscription.subscription_id)
            else:
                # Non-immediate subscriptions are handled by scheduler
                successful_subscriptions.append(subscription.subscription_id)
        
        # Only fail if there are subscriptions that want retry and failed
        if failed_subscriptions:
            logger.error("Some subscriptions failed and requested retry",
                        user_id=user_id,
                        event_id=event.event_id,
                        failed_subscriptions=failed_subscriptions,
                        successful_subscriptions=successful_subscriptions,
                        correlation_id=correlation_id)
            raise Exception(f"Delivery failed for user {user_id} subscriptions: {failed_subscriptions}")
        
        # Only purge events if user has ONLY immediate subscriptions (no aggregated ones)
        immediate_subscriptions = [sub for sub in user_subscriptions if sub.aggregation_frequency == AggregationFrequency.IMMEDIATE]
        aggregated_subscriptions = [sub for sub in user_subscriptions if sub.aggregation_frequency != AggregationFrequency.IMMEDIATE]
        
        # Only clear events if:
        # 1. User has immediate subscriptions that all succeeded, AND
        # 2. User has NO aggregated subscriptions (otherwise keep for aggregation)
        if (immediate_subscriptions and 
            all(sub.subscription_id in successful_subscriptions for sub in immediate_subscriptions) and
            not aggregated_subscriptions):
            try:
                # Clear this specific event since it was successfully delivered immediately
                # and user has no aggregated subscriptions
                self.event_store.clear_user_events(user_id, event.timestamp + timedelta(seconds=1))
                logger.info("Event data purged after successful immediate delivery (user has no aggregated subscriptions)",
                           user_id=user_id,
                           event_id=event.event_id,
                           immediate_subs=len(immediate_subscriptions),
                           aggregated_subs=len(aggregated_subscriptions),
                           correlation_id=correlation_id)
            except Exception as e:
                logger.warning("Failed to purge event data after delivery - event may be reprocessed",
                              user_id=user_id,
                              event_id=event.event_id,
                              error=str(e),
                              correlation_id=correlation_id)
        
        logger.info("All subscriptions processed successfully for user",
                   user_id=user_id,
                   event_id=event.event_id,
                   subscription_count=len(user_subscriptions),
                   successful_subscriptions=successful_subscriptions,
                   correlation_id=correlation_id)
    
    def start_listening(self):
        """Start listening to Pub/Sub messages"""
        logger.info("Starting Pub/Sub listener",
                   subscription_path=self.subscription_path,
                   project_id=self.project_id)
        
        # Flow control settings
        flow_control = pubsub_v1.types.FlowControl(max_messages=100)
        
        # Start streaming pull
        streaming_pull_future = self.subscriber.subscribe(
            self.subscription_path,
            callback=self.process_message,
            flow_control=flow_control,
        )
        
        logger.info("Pub/Sub listener active",
                   subscription_path=self.subscription_path)
        
        # Keep the main thread running
        try:
            streaming_pull_future.result()
        except KeyboardInterrupt:
            streaming_pull_future.cancel()
            logger.info("Pub/Sub subscription cancelled")

class ScheduledDeliveryService:
    """Handles scheduled delivery of aggregated events"""
    
    def __init__(self, event_store: EventStore, delivery_service: DeliveryService):
        self.event_store = event_store
        self.delivery_service = delivery_service
        self.aggregator = EventAggregator(event_store)
    
    def deliver_daily_aggregates(self):
        """Process and deliver daily aggregates for all users"""
        logger.info("Starting daily aggregates processing")
        
        preferences = self.event_store.get_all_preferences()
        now = datetime.now()
        yesterday = now - timedelta(days=1)
        
        for preference in preferences:
            if preference.aggregation_frequency != AggregationFrequency.DAILY:
                continue
            
            # Get events from yesterday
            events = self.event_store.get_user_events(preference.user_id, yesterday)
            
            if not events:
                continue
            
            # Aggregate and deliver
            content = self.aggregator.aggregate_events(preference.user_id, events, preference.aggregation_method)
            # For aggregated messages, use a generic subject and sender
            subject = f"Daily Summary - {len(events)} events"
            sender = "arXiv Messaging System"
            success = self.delivery_service.deliver(preference, content, subject, sender)
            
            if success:
                # Clear delivered events
                self.event_store.clear_user_events(preference.user_id, now)
                logger.info("Daily aggregate delivered",
                           user_id=preference.user_id,
                           events_count=len(events))
    
    def deliver_weekly_aggregates(self):
        """Process and deliver weekly aggregates for all users"""
        logger.info("Starting weekly aggregates processing")
        
        preferences = self.event_store.get_all_preferences()
        now = datetime.now()
        week_ago = now - timedelta(weeks=1)
        
        for preference in preferences:
            if preference.aggregation_frequency != AggregationFrequency.WEEKLY:
                continue
            
            # Get events from last week
            events = self.event_store.get_user_events(preference.user_id, week_ago)
            
            if not events:
                continue
            
            # Aggregate and deliver
            content = self.aggregator.aggregate_events(preference.user_id, events, preference.aggregation_method)
            # For aggregated messages, use a generic subject and sender
            subject = f"Weekly Summary - {len(events)} events"
            sender = "arXiv Messaging System"
            success = self.delivery_service.deliver(preference, content, subject, sender)
            
            if success:
                # Clear delivered events
                self.event_store.clear_user_events(preference.user_id, now)
                logger.info("Weekly aggregate delivered",
                           user_id=preference.user_id,
                           events_count=len(events))
    
    def deliver_hourly_aggregates(self):
        """Process and deliver hourly aggregates for all users"""
        logger.info("Starting hourly aggregates processing")
        
        preferences = self.event_store.get_all_preferences()
        now = datetime.now()
        hour_ago = now - timedelta(hours=1)
        
        for preference in preferences:
            if preference.aggregation_frequency != AggregationFrequency.HOURLY:
                continue
            
            # Get events from the past hour
            events = self.event_store.get_user_events(preference.user_id, hour_ago)
            
            if not events:
                continue
            
            # Aggregate and deliver
            content = self.aggregator.aggregate_events(preference.user_id, events, preference.aggregation_method)
            # For aggregated messages, use a generic subject and sender
            subject = f"Hourly Summary - {len(events)} events"
            sender = "arXiv Messaging System"
            success = self.delivery_service.deliver(preference, content, subject, sender)
            
            if success:
                # Clear delivered events
                self.event_store.clear_user_events(preference.user_id, now)
                logger.info("Hourly aggregate delivered",
                           user_id=preference.user_id,
                           events_count=len(events))
    
    def start_scheduler(self):
        """Start the scheduler for periodic deliveries"""
        # Schedule hourly aggregates at the top of each hour
        schedule.every().hour.at(":00").do(self.deliver_hourly_aggregates)
        
        # Schedule daily aggregates at 9 AM
        schedule.every().day.at("09:00").do(self.deliver_daily_aggregates)
        
        # Schedule weekly aggregates on Monday at 9 AM
        schedule.every().monday.at("09:00").do(self.deliver_weekly_aggregates)
        
        logger.info("Event aggregation scheduler started")
        
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute

class EventAggregationSystem:
    """Main system orchestrator"""
    
    def __init__(self, project_id: str, subscription_name: str, database_id: str = "messaging"):
        self.event_store = EventStore(project_id, database_id)
        self.delivery_service = DeliveryService()
        self.pubsub_processor = PubSubEventProcessor(
            project_id, subscription_name, self.event_store, self.delivery_service
        )
        self.scheduled_delivery = ScheduledDeliveryService(
            self.event_store, self.delivery_service
        )
    
    def add_user_preference(self, preference: UserPreference):
        """Add or update user preference"""
        self.event_store.store_user_preference(preference)
    
    def start(self):
        """Start the entire system"""
        logger.info("Starting Event Aggregation System",
                   project_id=self.pubsub_processor.project_id,
                   subscription=self.pubsub_processor.subscription_name)
        
        # Start scheduler in a separate thread
        scheduler_thread = threading.Thread(target=self.scheduled_delivery.start_scheduler)
        scheduler_thread.daemon = True
        scheduler_thread.start()
        
        # Start Pub/Sub listener (blocking)
        self.pubsub_processor.start_listening()

# Example usage and testing
if __name__ == "__main__":
    # Initialize the system
    system = EventAggregationSystem(
        project_id="your-gcp-project",
        subscription_name="event-subscription"
    )
    
    # Add user preferences
    user1_preference = UserPreference(
        user_id="user_123",
        delivery_method=DeliveryMethod.EMAIL,
        aggregation_frequency=AggregationFrequency.DAILY,
        delivery_time="09:00",
        timezone="UTC",
        email_address="user123@arxiv.org"
    )
    
    user2_preference = UserPreference(
        user_id="user_456",
        delivery_method=DeliveryMethod.SLACK,
        aggregation_frequency=AggregationFrequency.IMMEDIATE,
        timezone="UTC",
    )
    
    system.add_user_preference(user1_preference)
    system.add_user_preference(user2_preference)
    
    logger.info("Example configuration:")
    logger.info("- User 123: Daily Email notifications")
    logger.info("- User 456: Immediate Slack notifications")
    
    # Start the system
    logger.info("System configured and ready to start...")
    # system.start()  # Uncomment to actually start the system
