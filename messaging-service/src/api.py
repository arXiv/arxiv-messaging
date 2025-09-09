"""
FastAPI REST API for managing undelivered messages
"""

from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
from datetime import datetime
import structlog
import os

from .message_server import EventStore, DeliveryService, EventAggregator
from arxiv_messaging import Event, EventType, Subscription, DeliveryMethod, AggregationFrequency, AggregationMethod, DeliveryErrorStrategy

# Configure structured logging
logger = structlog.get_logger(__name__)

app = FastAPI(
    title="arXiv Messaging Service API",
    description="REST API for managing undelivered messages and user subscriptions",
    version="1.0.0"
)

# Pydantic models for API responses
class UserStats(BaseModel):
    user_id: str
    subscription_count: int
    undelivered_count: int
    enabled_subscriptions: int

class EventResponse(BaseModel):
    event_id: str
    user_id: str
    event_type: str
    message: str
    sender: str
    subject: str
    timestamp: datetime
    metadata: Dict[str, Any]

class UndeliveredStats(BaseModel):
    total_users_with_undelivered: int
    total_undelivered_events: int
    users_with_counts: Dict[str, int]
    events_by_type: Dict[str, int]

class FlushRequest(BaseModel):
    user_id: Optional[str] = None
    force_delivery: bool = False
    dry_run: bool = False

class FlushResponse(BaseModel):
    users_processed: int
    messages_delivered: int
    messages_failed: int
    events_cleared: int
    errors: List[str]
    dry_run: bool

class DeleteRequest(BaseModel):
    user_id: Optional[str] = None
    event_ids: Optional[List[str]] = None
    before_timestamp: Optional[datetime] = None

class DeleteResponse(BaseModel):
    events_deleted: int
    users_affected: List[str]

class SubscriptionResponse(BaseModel):
    subscription_id: str
    user_id: str
    delivery_method: str
    aggregation_frequency: str
    aggregation_method: str
    delivery_error_strategy: str
    delivery_time: str
    timezone: str
    email_address: Optional[str] = None
    slack_webhook_url: Optional[str] = None
    enabled: bool

class CreateSubscriptionRequest(BaseModel):
    user_id: str
    delivery_method: str  # EMAIL or SLACK
    aggregation_frequency: str  # IMMEDIATE, HOURLY, DAILY, WEEKLY
    aggregation_method: str = "PLAIN"  # PLAIN, HTML, MIME
    delivery_error_strategy: str = "RETRY"  # RETRY, IGNORE
    delivery_time: str = "09:00"
    timezone: str = "UTC"
    email_address: Optional[str] = None
    slack_webhook_url: Optional[str] = None
    enabled: bool = True

class UpdateSubscriptionRequest(BaseModel):
    delivery_method: Optional[str] = None
    aggregation_frequency: Optional[str] = None
    aggregation_method: Optional[str] = None
    delivery_error_strategy: Optional[str] = None
    delivery_time: Optional[str] = None
    timezone: Optional[str] = None
    email_address: Optional[str] = None
    slack_webhook_url: Optional[str] = None
    enabled: Optional[bool] = None

# Dependency injection for services
async def get_event_store() -> EventStore:
    """Get EventStore instance"""
    project_id = os.getenv('GCP_PROJECT_ID')
    database_id = os.getenv('FIRESTORE_DATABASE_ID', 'messaging')
    
    if not project_id:
        raise HTTPException(status_code=500, detail="GCP_PROJECT_ID not configured")
    
    return EventStore(project_id, database_id)

async def get_services():
    """Get all required services"""
    event_store = await get_event_store()
    delivery_service = DeliveryService()
    aggregator = EventAggregator(event_store)
    return event_store, delivery_service, aggregator

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "arxiv-messaging-api"}

@app.get("/users", response_model=List[UserStats])
async def list_users(
    event_store: EventStore = Depends(get_event_store),
    include_empty: bool = Query(False, description="Include users with no undelivered messages")
):
    """
    1st endpoint: List all users with their subscription and undelivered message counts
    """
    try:
        logger.info("API: Listing users", include_empty=include_empty)
        
        # Get all undelivered events grouped by user
        undelivered_events = event_store.get_undelivered_events()
        
        # Get all users who have subscriptions
        all_users = set()
        
        # Get users from undelivered events
        all_users.update(undelivered_events.keys())
        
        # If include_empty, we need to get all users with subscriptions
        if include_empty:
            # This would require a method to get all users with subscriptions
            # For now, we'll work with users who have undelivered messages
            pass
        
        user_stats = []
        for user_id in all_users:
            try:
                # Get user subscriptions
                subscriptions = event_store.get_user_subscriptions(user_id)
                enabled_subs = [sub for sub in subscriptions if sub.enabled]
                
                undelivered_count = len(undelivered_events.get(user_id, []))
                
                # Skip users with no undelivered messages if not requested
                if not include_empty and undelivered_count == 0:
                    continue
                
                user_stats.append(UserStats(
                    user_id=user_id,
                    subscription_count=len(subscriptions),
                    undelivered_count=undelivered_count,
                    enabled_subscriptions=len(enabled_subs)
                ))
                
            except Exception as e:
                logger.warning("Error getting stats for user", user_id=user_id, error=str(e))
                continue
        
        logger.info("API: Listed users", total_users=len(user_stats))
        return user_stats
        
    except Exception as e:
        logger.error("API: Failed to list users", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to list users: {str(e)}")

@app.get("/users/{user_id}/messages", response_model=List[EventResponse])
async def get_user_messages(
    user_id: str,
    event_store: EventStore = Depends(get_event_store),
    limit: Optional[int] = Query(None, description="Maximum number of messages to return"),
    event_type: Optional[str] = Query(None, description="Filter by event type")
):
    """
    2nd endpoint: Get undelivered messages for a specific user
    """
    try:
        logger.info("API: Getting user messages", 
                   user_id=user_id, limit=limit, event_type=event_type)
        
        events = event_store.get_undelivered_events_by_user(user_id)
        
        if not events:
            return []
        
        # Apply filters
        filtered_events = []
        for event in events:
            # Apply event type filter if specified
            if event_type and event.event_type.value != event_type.upper():
                continue
            filtered_events.append(event)
            
            # Apply limit
            if limit and len(filtered_events) >= limit:
                break
        
        event_responses = [
            EventResponse(
                event_id=event.event_id,
                user_id=event.user_id,
                event_type=event.event_type.value,
                message=event.message,
                sender=event.sender,
                subject=event.subject,
                timestamp=event.timestamp,
                metadata=event.metadata
            )
            for event in filtered_events
        ]
        
        logger.info("API: Retrieved user messages", 
                   user_id=user_id, message_count=len(event_responses))
        return event_responses
        
    except Exception as e:
        logger.error("API: Failed to get user messages", 
                    user_id=user_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get messages for user: {str(e)}")

@app.get("/undelivered", response_model=List[EventResponse])
async def list_all_undelivered_messages(
    event_store: EventStore = Depends(get_event_store),
    limit: Optional[int] = Query(100, description="Maximum number of events to return"),
    event_type: Optional[str] = Query(None, description="Filter by event type")
):
    """
    List all undelivered messages across all users (for admin/monitoring)
    """
    try:
        logger.info("API: Listing all undelivered messages", 
                   limit=limit, event_type=event_type)
        
        # Get all undelivered events
        undelivered_events = event_store.get_undelivered_events(limit)
        
        # Convert to response format
        event_responses = []
        total_processed = 0
        
        for uid, events in undelivered_events.items():
            for event in events:
                # Apply event type filter if specified
                if event_type and event.event_type.value != event_type.upper():
                    continue
                
                # Apply limit
                if limit and total_processed >= limit:
                    break
                    
                event_responses.append(EventResponse(
                    event_id=event.event_id,
                    user_id=event.user_id,
                    event_type=event.event_type.value,
                    message=event.message,
                    sender=event.sender,
                    subject=event.subject,
                    timestamp=event.timestamp,
                    metadata=event.metadata
                ))
                total_processed += 1
            
            if limit and total_processed >= limit:
                break
        
        logger.info("API: Listed all undelivered messages", 
                   total_events=len(event_responses))
        return event_responses
        
    except Exception as e:
        logger.error("API: Failed to list all undelivered messages", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to list undelivered messages: {str(e)}")

@app.get("/undelivered/stats", response_model=UndeliveredStats)
async def get_undelivered_stats(
    event_store: EventStore = Depends(get_event_store)
):
    """
    Get statistics about undelivered messages
    """
    try:
        logger.info("API: Getting undelivered stats")
        
        stats = event_store.get_undelivered_stats()
        
        return UndeliveredStats(
            total_users_with_undelivered=stats.get('total_users_with_undelivered', 0),
            total_undelivered_events=stats.get('total_undelivered_events', 0),
            users_with_counts=stats.get('users_with_counts', {}),
            events_by_type=stats.get('events_by_type', {})
        )
        
    except Exception as e:
        logger.error("API: Failed to get undelivered stats", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")

@app.post("/flush", response_model=FlushResponse)
async def flush_messages(
    request: FlushRequest,
    event_store: EventStore = Depends(get_event_store)
):
    """
    3rd endpoint: Flush undelivered messages
    """
    try:
        logger.info("API: Flushing messages", 
                   user_id=request.user_id, 
                   force_delivery=request.force_delivery,
                   dry_run=request.dry_run)
        
        if request.dry_run:
            # Dry run - just return what would be processed
            if request.user_id:
                events = event_store.get_undelivered_events_by_user(request.user_id)
                undelivered_events = {request.user_id: events} if events else {}
            else:
                undelivered_events = event_store.get_undelivered_events()
            
            users_processed = len(undelivered_events)
            total_events = sum(len(events) for events in undelivered_events.values())
            
            return FlushResponse(
                users_processed=users_processed,
                messages_delivered=0,
                messages_failed=0,
                events_cleared=0,
                errors=[],
                dry_run=True
            )
        
        # Actual flush
        delivery_service = DeliveryService()
        aggregator = EventAggregator(event_store)
        
        results = event_store.flush_undelivered_messages(
            delivery_service=delivery_service,
            aggregator=aggregator,
            user_id=request.user_id,
            force_delivery=request.force_delivery
        )
        
        logger.info("API: Flush completed", **results)
        
        return FlushResponse(
            users_processed=results['users_processed'],
            messages_delivered=results['messages_delivered'],
            messages_failed=results['messages_failed'],
            events_cleared=results['events_cleared'],
            errors=results['errors'],
            dry_run=False
        )
        
    except Exception as e:
        logger.error("API: Failed to flush messages", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to flush messages: {str(e)}")

@app.get("/users/{user_id}/messages/{message_id}", response_model=EventResponse)
async def get_user_message(
    user_id: str,
    message_id: str,
    event_store: EventStore = Depends(get_event_store)
):
    """
    4th endpoint: Get a specific message for a user
    """
    try:
        logger.info("API: Getting specific user message", 
                   user_id=user_id, message_id=message_id)
        
        # Get all events for user to find the specific message
        events = event_store.get_undelivered_events_by_user(user_id)
        
        # Find the specific message
        target_event = None
        for event in events:
            if event.event_id == message_id:
                target_event = event
                break
        
        if not target_event:
            raise HTTPException(
                status_code=404, 
                detail=f"Message {message_id} not found for user {user_id}"
            )
        
        response = EventResponse(
            event_id=target_event.event_id,
            user_id=target_event.user_id,
            event_type=target_event.event_type.value,
            message=target_event.message,
            sender=target_event.sender,
            subject=target_event.subject,
            timestamp=target_event.timestamp,
            metadata=target_event.metadata
        )
        
        logger.info("API: Retrieved specific user message", 
                   user_id=user_id, message_id=message_id)
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("API: Failed to get specific user message", 
                    user_id=user_id, message_id=message_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get message: {str(e)}")

@app.delete("/users/{user_id}/messages/{message_id}")
async def delete_user_message(
    user_id: str,
    message_id: str,
    event_store: EventStore = Depends(get_event_store)
):
    """
    5th endpoint: Delete a specific message for a user
    """
    try:
        logger.info("API: Deleting specific user message", 
                   user_id=user_id, message_id=message_id)
        
        # First verify the message belongs to this user
        events = event_store.get_undelivered_events_by_user(user_id)
        message_found = any(event.event_id == message_id for event in events)
        
        if not message_found:
            raise HTTPException(
                status_code=404, 
                detail=f"Message {message_id} not found for user {user_id}"
            )
        
        # Delete the specific event
        success = event_store.delete_event_by_id(message_id)
        
        if not success:
            raise HTTPException(
                status_code=500, 
                detail=f"Failed to delete message {message_id}"
            )
        
        logger.info("API: Deleted specific user message", 
                   user_id=user_id, message_id=message_id)
        
        return {
            "message": "Message deleted successfully",
            "user_id": user_id,
            "message_id": message_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("API: Failed to delete specific user message", 
                    user_id=user_id, message_id=message_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to delete message: {str(e)}")

@app.delete("/users/{user_id}/messages")
async def delete_user_messages(
    user_id: str,
    event_store: EventStore = Depends(get_event_store),
    before_timestamp: Optional[datetime] = Query(None, description="Delete messages before this timestamp")
):
    """
    Delete all messages for a user, optionally before a specific timestamp
    """
    try:
        logger.info("API: Deleting user messages", 
                   user_id=user_id, before_timestamp=before_timestamp)
        
        if before_timestamp:
            # Delete messages before timestamp
            event_store.clear_user_events(user_id, before_timestamp)
            message = f"Messages deleted for user {user_id} before {before_timestamp}"
        else:
            # Delete all messages for user
            event_store.clear_user_events(user_id, datetime.now())
            message = f"All messages deleted for user {user_id}"
        
        logger.info("API: Deleted user messages", 
                   user_id=user_id, before_timestamp=before_timestamp)
        
        return {
            "message": message,
            "user_id": user_id,
            "before_timestamp": before_timestamp.isoformat() if before_timestamp else None
        }
        
    except Exception as e:
        logger.error("API: Failed to delete user messages", 
                    user_id=user_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to delete messages: {str(e)}")

@app.delete("/undelivered", response_model=DeleteResponse)
async def delete_messages(
    request: DeleteRequest,
    event_store: EventStore = Depends(get_event_store)
):
    """
    5th endpoint: Delete undelivered messages
    """
    try:
        logger.info("API: Deleting messages", 
                   user_id=request.user_id,
                   event_ids=request.event_ids,
                   before_timestamp=request.before_timestamp)
        
        events_deleted = 0
        users_affected = set()
        
        if request.event_ids:
            # Delete specific events by ID
            delete_result = event_store.delete_events_by_ids(request.event_ids)
            events_deleted = delete_result['deleted_count']
            
            # Get affected users by checking which events were deleted
            # This is a simplified approach - in practice you might want to track this better
            if events_deleted > 0:
                users_affected.add("multiple_users")  # Placeholder since we don't track user per event in bulk delete
                    
        elif request.user_id and request.before_timestamp:
            # Delete events for specific user before timestamp
            try:
                event_store.clear_user_events(request.user_id, request.before_timestamp)
                users_affected.add(request.user_id)
                # We don't have an exact count, so we'll estimate
                events_deleted = 1  # Placeholder
            except Exception as e:
                logger.error("Failed to clear user events", 
                           user_id=request.user_id, error=str(e))
                raise
                
        elif request.user_id:
            # Delete all events for specific user
            try:
                event_store.clear_user_events(request.user_id, datetime.now())
                users_affected.add(request.user_id)
                events_deleted = 1  # Placeholder
            except Exception as e:
                logger.error("Failed to clear user events", 
                           user_id=request.user_id, error=str(e))
                raise
                
        elif request.before_timestamp:
            # Delete all events before timestamp (dangerous operation)
            logger.warning("Global event deletion requested", 
                         before_timestamp=request.before_timestamp)
            raise HTTPException(
                status_code=400, 
                detail="Global deletion by timestamp not implemented for safety"
            )
        else:
            raise HTTPException(
                status_code=400,
                detail="Must specify either user_id, event_ids, or before_timestamp"
            )
        
        logger.info("API: Messages deleted", 
                   events_deleted=events_deleted,
                   users_affected=len(users_affected))
        
        return DeleteResponse(
            events_deleted=events_deleted,
            users_affected=list(users_affected)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("API: Failed to delete messages", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to delete messages: {str(e)}")

# Subscription Management Endpoints

@app.get("/users/{user_id}/subscriptions", response_model=List[SubscriptionResponse])
async def get_user_subscriptions(
    user_id: str,
    event_store: EventStore = Depends(get_event_store)
):
    """
    Get all subscriptions for a user
    """
    try:
        logger.info("API: Getting user subscriptions", user_id=user_id)
        
        subscriptions = event_store.get_user_subscriptions(user_id)
        
        subscription_responses = [
            SubscriptionResponse(
                subscription_id=sub.subscription_id,
                user_id=sub.user_id,
                delivery_method=sub.delivery_method.value,
                aggregation_frequency=sub.aggregation_frequency.value,
                aggregation_method=sub.aggregation_method.value,
                delivery_error_strategy=sub.delivery_error_strategy.value,
                delivery_time=sub.delivery_time,
                timezone=sub.timezone,
                email_address=sub.email_address,
                slack_webhook_url=sub.slack_webhook_url,
                enabled=sub.enabled
            )
            for sub in subscriptions
        ]
        
        logger.info("API: Retrieved user subscriptions", 
                   user_id=user_id, subscription_count=len(subscription_responses))
        return subscription_responses
        
    except Exception as e:
        logger.error("API: Failed to get user subscriptions", 
                    user_id=user_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get subscriptions: {str(e)}")

@app.post("/users/{user_id}/subscriptions", response_model=SubscriptionResponse)
async def create_user_subscription(
    user_id: str,
    request: CreateSubscriptionRequest,
    event_store: EventStore = Depends(get_event_store)
):
    """
    Create a new subscription for a user
    """
    try:
        logger.info("API: Creating user subscription", user_id=user_id)
        
        # Validate that user_id in path matches request
        if user_id != request.user_id:
            raise HTTPException(
                status_code=400, 
                detail="User ID in path must match user ID in request body"
            )
        
        # Validate delivery method requirements
        if request.delivery_method.upper() == "EMAIL" and not request.email_address:
            raise HTTPException(
                status_code=400,
                detail="Email address is required for email delivery method"
            )
        
        if request.delivery_method.upper() == "SLACK" and not request.slack_webhook_url:
            raise HTTPException(
                status_code=400,
                detail="Slack webhook URL is required for slack delivery method"
            )
        
        # Generate subscription ID
        subscription_id = f"{user_id}-{request.delivery_method.lower()}-{int(datetime.now().timestamp())}"
        
        # Create subscription object
        subscription = Subscription(
            subscription_id=subscription_id,
            user_id=request.user_id,
            delivery_method=DeliveryMethod(request.delivery_method.upper()),
            aggregation_frequency=AggregationFrequency(request.aggregation_frequency.upper()),
            aggregation_method=AggregationMethod(request.aggregation_method.upper()),
            delivery_error_strategy=DeliveryErrorStrategy(request.delivery_error_strategy.upper()),
            delivery_time=request.delivery_time,
            timezone=request.timezone,
            email_address=request.email_address,
            slack_webhook_url=request.slack_webhook_url,
            enabled=request.enabled
        )
        
        # Store subscription
        event_store.store_subscription(subscription)
        
        response = SubscriptionResponse(
            subscription_id=subscription.subscription_id,
            user_id=subscription.user_id,
            delivery_method=subscription.delivery_method.value,
            aggregation_frequency=subscription.aggregation_frequency.value,
            aggregation_method=subscription.aggregation_method.value,
            delivery_error_strategy=subscription.delivery_error_strategy.value,
            delivery_time=subscription.delivery_time,
            timezone=subscription.timezone,
            email_address=subscription.email_address,
            slack_webhook_url=subscription.slack_webhook_url,
            enabled=subscription.enabled
        )
        
        logger.info("API: Created user subscription", 
                   user_id=user_id, subscription_id=subscription_id)
        return response
        
    except ValueError as e:
        logger.error("API: Invalid subscription parameters", 
                    user_id=user_id, error=str(e))
        raise HTTPException(status_code=400, detail=f"Invalid parameters: {str(e)}")
    except Exception as e:
        logger.error("API: Failed to create user subscription", 
                    user_id=user_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to create subscription: {str(e)}")

@app.get("/users/{user_id}/subscriptions/{subscription_id}", response_model=SubscriptionResponse)
async def get_user_subscription(
    user_id: str,
    subscription_id: str,
    event_store: EventStore = Depends(get_event_store)
):
    """
    Get a specific subscription for a user
    """
    try:
        logger.info("API: Getting specific user subscription", 
                   user_id=user_id, subscription_id=subscription_id)
        
        subscriptions = event_store.get_user_subscriptions(user_id)
        
        # Find the specific subscription
        target_subscription = None
        for sub in subscriptions:
            if sub.subscription_id == subscription_id:
                target_subscription = sub
                break
        
        if not target_subscription:
            raise HTTPException(
                status_code=404,
                detail=f"Subscription {subscription_id} not found for user {user_id}"
            )
        
        response = SubscriptionResponse(
            subscription_id=target_subscription.subscription_id,
            user_id=target_subscription.user_id,
            delivery_method=target_subscription.delivery_method.value,
            aggregation_frequency=target_subscription.aggregation_frequency.value,
            aggregation_method=target_subscription.aggregation_method.value,
            delivery_error_strategy=target_subscription.delivery_error_strategy.value,
            delivery_time=target_subscription.delivery_time,
            timezone=target_subscription.timezone,
            email_address=target_subscription.email_address,
            slack_webhook_url=target_subscription.slack_webhook_url,
            enabled=target_subscription.enabled
        )
        
        logger.info("API: Retrieved specific user subscription", 
                   user_id=user_id, subscription_id=subscription_id)
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("API: Failed to get specific user subscription", 
                    user_id=user_id, subscription_id=subscription_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get subscription: {str(e)}")

@app.put("/users/{user_id}/subscriptions/{subscription_id}", response_model=SubscriptionResponse)
async def update_user_subscription(
    user_id: str,
    subscription_id: str,
    request: UpdateSubscriptionRequest,
    event_store: EventStore = Depends(get_event_store)
):
    """
    Update a specific subscription for a user
    """
    try:
        logger.info("API: Updating user subscription", 
                   user_id=user_id, subscription_id=subscription_id)
        
        # Get existing subscription
        subscriptions = event_store.get_user_subscriptions(user_id)
        target_subscription = None
        for sub in subscriptions:
            if sub.subscription_id == subscription_id:
                target_subscription = sub
                break
        
        if not target_subscription:
            raise HTTPException(
                status_code=404,
                detail=f"Subscription {subscription_id} not found for user {user_id}"
            )
        
        # Update fields that are provided
        if request.delivery_method is not None:
            target_subscription.delivery_method = DeliveryMethod(request.delivery_method.upper())
        if request.aggregation_frequency is not None:
            target_subscription.aggregation_frequency = AggregationFrequency(request.aggregation_frequency.upper())
        if request.aggregation_method is not None:
            target_subscription.aggregation_method = AggregationMethod(request.aggregation_method.upper())
        if request.delivery_error_strategy is not None:
            target_subscription.delivery_error_strategy = DeliveryErrorStrategy(request.delivery_error_strategy.upper())
        if request.delivery_time is not None:
            target_subscription.delivery_time = request.delivery_time
        if request.timezone is not None:
            target_subscription.timezone = request.timezone
        if request.email_address is not None:
            target_subscription.email_address = request.email_address
        if request.slack_webhook_url is not None:
            target_subscription.slack_webhook_url = request.slack_webhook_url
        if request.enabled is not None:
            target_subscription.enabled = request.enabled
        
        # Validate delivery method requirements
        if target_subscription.delivery_method == DeliveryMethod.EMAIL and not target_subscription.email_address:
            raise HTTPException(
                status_code=400,
                detail="Email address is required for email delivery method"
            )
        
        if target_subscription.delivery_method == DeliveryMethod.SLACK and not target_subscription.slack_webhook_url:
            raise HTTPException(
                status_code=400,
                detail="Slack webhook URL is required for slack delivery method"
            )
        
        # Store updated subscription
        event_store.store_subscription(target_subscription)
        
        response = SubscriptionResponse(
            subscription_id=target_subscription.subscription_id,
            user_id=target_subscription.user_id,
            delivery_method=target_subscription.delivery_method.value,
            aggregation_frequency=target_subscription.aggregation_frequency.value,
            aggregation_method=target_subscription.aggregation_method.value,
            delivery_error_strategy=target_subscription.delivery_error_strategy.value,
            delivery_time=target_subscription.delivery_time,
            timezone=target_subscription.timezone,
            email_address=target_subscription.email_address,
            slack_webhook_url=target_subscription.slack_webhook_url,
            enabled=target_subscription.enabled
        )
        
        logger.info("API: Updated user subscription", 
                   user_id=user_id, subscription_id=subscription_id)
        return response
        
    except HTTPException:
        raise
    except ValueError as e:
        logger.error("API: Invalid subscription update parameters", 
                    user_id=user_id, subscription_id=subscription_id, error=str(e))
        raise HTTPException(status_code=400, detail=f"Invalid parameters: {str(e)}")
    except Exception as e:
        logger.error("API: Failed to update user subscription", 
                    user_id=user_id, subscription_id=subscription_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to update subscription: {str(e)}")

@app.delete("/users/{user_id}/subscriptions/{subscription_id}")
async def delete_user_subscription(
    user_id: str,
    subscription_id: str,
    event_store: EventStore = Depends(get_event_store)
):
    """
    Delete a specific subscription for a user
    """
    try:
        logger.info("API: Deleting user subscription", 
                   user_id=user_id, subscription_id=subscription_id)
        
        # Verify the subscription exists and belongs to the user
        subscriptions = event_store.get_user_subscriptions(user_id)
        subscription_exists = any(sub.subscription_id == subscription_id for sub in subscriptions)
        
        if not subscription_exists:
            raise HTTPException(
                status_code=404,
                detail=f"Subscription {subscription_id} not found for user {user_id}"
            )
        
        # Delete the subscription (we need to add this method to EventStore)
        success = event_store.delete_subscription(subscription_id)
        
        if not success:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to delete subscription {subscription_id}"
            )
        
        logger.info("API: Deleted user subscription", 
                   user_id=user_id, subscription_id=subscription_id)
        
        return {
            "message": "Subscription deleted successfully",
            "user_id": user_id,
            "subscription_id": subscription_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("API: Failed to delete user subscription", 
                    user_id=user_id, subscription_id=subscription_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to delete subscription: {str(e)}")

# Error handlers
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error("Unhandled API exception", 
                path=str(request.url),
                method=request.method,
                error=str(exc))
    
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error", 
            "error": str(exc)
        }
    )

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv('API_PORT', 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)