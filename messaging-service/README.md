# arXiv Messaging Service

A GCP Cloud Run service that processes messaging events via Pub/Sub and delivers notifications through email (SMTP) and Slack (webhooks). The service supports real-time delivery, scheduled aggregation, and on-demand flushing of undelivered messages.

## Architecture Overview

### Service Components

1. **PubSubEventProcessor** - Handles incoming Pub/Sub messages
2. **EventStore** - Manages Firestore persistence and undelivered message tracking
3. **DeliveryService** - Routes messages to appropriate delivery providers
4. **EventAggregator** - Formats messages using different aggregation methods
5. **ScheduledDeliveryService** - Handles periodic batch delivery

### Cloud Run Integration

The service runs as a long-running Cloud Run container with:
- **HTTP health endpoint** (`:8080/health`) for Cloud Run health checks
- **Continuous Pub/Sub processing** in the main thread
- **Graceful shutdown** handling for container lifecycle

## Message Flushing Architecture

### What is Message Flushing?

Message flushing is the process of delivering accumulated undelivered messages that remain in Firestore storage. Messages become "undelivered" when:
- Initial delivery attempts fail due to SMTP/webhook errors
- Service restarts before processing queued messages
- Network issues prevent delivery completion
- User subscription configuration issues

### Flushing Communication Pattern

**Important**: The messaging service itself does **NOT** expose HTTP APIs for flushing. Instead, flushing is performed by **external CLI tools** that directly access the same backend resources.

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   CLI Command   │    │   Firestore DB   │    │ Messaging Srv   │
│ (External Tool) │    │   (Shared)       │    │ (Cloud Run)     │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                       │                       │
         │ 1. Query undelivered  │                       │
         │    events             │                       │
         ├──────────────────────►│                       │
         │                       │                       │
         │ 2. Get subscriptions  │                       │
         ├──────────────────────►│                       │
         │                       │                       │
         │ 3. Flush via SMTP/    │                       │
         │    HTTP webhooks      │                       │
         ├───────────────────────┼──────────────────────►│
         │                       │                       │ SMTP/Webhook
         │ 4. Clear events       │                       │ Delivery
         │    after success      │                       │
         ├──────────────────────►│                       │
         │                       │                       │
```

### Database-Centric Communication

Unlike typical microservice architectures that use HTTP APIs, this system uses a **database-centric pattern**:

1. **Shared Firestore Access**: Both the service and CLI tools access the same Firestore database
2. **Direct Resource Access**: CLI tools directly connect to SMTP servers and Slack webhooks
3. **No Service API**: No HTTP communication between CLI and messaging service
4. **Atomic Operations**: Firestore transactions ensure consistency

### Flushing Implementation Details

#### EventStore.flush_undelivered_messages()

Located in `src/message_server.py:573-716`, this method performs the complete flush operation:

```python
def flush_undelivered_messages(
    self, 
    delivery_service: DeliveryService, 
    aggregator: EventAggregator, 
    user_id: str = None, 
    force_delivery: bool = False
) -> Dict[str, Any]
```

**Step-by-Step Process:**

1. **Query Undelivered Events**
   ```python
   # Get all events from Firestore events collection
   undelivered_events = self.get_undelivered_events()
   ```

2. **User Subscription Retrieval**
   ```python
   # Get delivery preferences for each user
   subscriptions = self.get_user_subscriptions(user_id)
   ```

3. **Event Aggregation**
   ```python
   # Format events according to user preferences
   content = aggregator.aggregate_events(
       user_id, events, subscription.aggregation_method
   )
   ```

4. **Delivery Execution**
   ```python
   # Send via SMTP or HTTP webhook
   success = delivery_service.deliver(
       subscription, content, subject, sender, correlation_id
   )
   ```

5. **Event Cleanup**
   ```python
   # Clear successfully delivered events
   if success:
       self.clear_user_events(user_id, datetime.now())
   ```

### Communication Protocols

#### SMTP Email Delivery (`src/email_sender.py`)

```python
def send_email(smtp_server, smtp_port, smtp_user, smtp_pass, 
               recipient, sender, subject, body, use_ssl=False):
    # SSL/TLS connection to SMTP server
    if use_ssl and smtp_port == 465:
        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(sender, recipient, message)
    else:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            if use_ssl:
                server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(sender, recipient, message)
```

**Configuration:**
- Default: `smtp-relay.gmail.com:465` with SSL
- Environment variables: `SMTP_SERVER`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`
- Support for both SSL (port 465) and STARTTLS

#### Slack Webhook Delivery (`src/message_server.py:136-200`)

```python
def send(self, user_preference, content, subject=None, sender=None):
    payload = {
        "subject": subject or "Notification",
        "message": content,
        "sender": sender
    }
    
    with httpx.Client(timeout=30) as client:
        response = client.post(
            user_preference.slack_webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
```

**Features:**
- 30-second HTTP timeout
- JSON payload format
- Error handling with retries based on `delivery_error_strategy`

### Aggregation Methods

The service supports three aggregation formats for flushed messages:

#### 1. PLAIN Text (`_aggregate_plain`)
```
Event Summary for User ntai
Period: 2023-12-01 to 2023-12-02
Total Events: 5
--------------------------------------------------

NOTIFICATION (3 events):
------------------------------
• 10:00 - Your submission was processed
• 11:30 - Build completed successfully
• 14:15 - Review comments available

ALERT (2 events):
------------------------------
• 09:45 - System maintenance scheduled
• 16:20 - Storage quota exceeded
```

#### 2. HTML Table (`_aggregate_html`)
```html
<!DOCTYPE html>
<html>
<head><title>Event Summary</title>
<style>
  table { border-collapse: collapse; width: 100%; }
  th, td { border: 1px solid #ddd; padding: 8px; }
  th { background-color: #f2f2f2; }
</style>
</head>
<body>
<h1>Event Summary for User ntai</h1>
<table>
  <tr><th>Timestamp</th><th>Event ID</th><th>Type</th><th>Subject</th></tr>
  <tr><td>2023-12-01 10:00</td><td>event-123</td><td>NOTIFICATION</td><td>Submission Processed</td></tr>
</table>
</body>
</html>
```

#### 3. MIME Multipart (`_aggregate_mime`)
```
Content-Type: multipart/mixed; boundary="boundary123"
Subject: Event Summary for User ntai
From: arXiv Messaging System

--boundary123
Content-Type: text/plain
Content-Disposition: inline; filename="summary.txt"

Event Summary for User ntai
Total Events: 5

--boundary123
Content-Type: text/plain  
Content-Disposition: inline; filename="NOTIFICATION_events.txt"

NOTIFICATION Events (3 total)
Event ID: event-123
Timestamp: 2023-12-01 10:00:00
Message: Your submission was processed
```

### CLI Integration

The flushing functionality is accessed through the `arxiv-manage-subscribers` CLI tool:

#### List Undelivered Messages
```bash
# Show statistics
arxiv-manage-subscribers undelivered list --stats-only

# Show detailed list
arxiv-manage-subscribers undelivered list --user-id ntai
```

#### Flush Messages
```bash
# Flush all undelivered messages
arxiv-manage-subscribers undelivered flush

# Flush specific user
arxiv-manage-subscribers undelivered flush --user-id ntai

# Dry run (no actual delivery)
arxiv-manage-subscribers undelivered flush --dry-run

# Force flush (clear events regardless of delivery success)
arxiv-manage-subscribers undelivered flush --force
```

### Error Handling and Reliability

#### Delivery Error Strategies
- **RETRY**: Keep events in storage for future flush attempts
- **IGNORE**: Clear events even if delivery fails

#### Correlation IDs
Every flush operation generates correlation IDs for tracking:
```python
correlation_id = f"flush-{user_id}-{int(datetime.now().timestamp())}"
```

#### Atomic Operations
Firestore transactions ensure events are only cleared after successful delivery:
```python
# Only clear events if delivery succeeds
if delivery_success:
    self.clear_user_events(user_id, datetime.now())
    events_cleared += len(events)
```

### Monitoring and Logging

The service uses structured JSON logging with correlation IDs:

```json
{
  "event": "flush_started",
  "total_users": 15,
  "total_events": 47,
  "target_user": "ntai",
  "force_delivery": false,
  "timestamp": "2023-12-01T10:00:00Z"
}

{
  "event": "flush_delivery_success", 
  "user_id": "ntai",
  "subscription_id": "ntai-email",
  "events_delivered": 5,
  "delivery_method": "email",
  "aggregation_method": "HTML",
  "correlation_id": "flush-ntai-1701421200"
}
```

### Deployment and Configuration

#### Environment Variables
```env
# Required
GCP_PROJECT_ID=arxiv-production
PUBSUB_SUBSCRIPTION_NAME=event-subscription
FIRESTORE_DATABASE_ID=messaging

# SMTP Configuration
SMTP_SERVER=smtp-relay.gmail.com
SMTP_PORT=465
SMTP_USER=smtp-relay@arxiv.org
SMTP_PASSWORD=your-smtp-password
SMTP_USE_SSL=true
DEFAULT_EMAIL_SENDER=arxiv-messaging@arxiv.org
```

#### Docker Deployment
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml poetry.lock* ./
RUN poetry install --only=main
COPY src/ ./src/
COPY main.py .
EXPOSE 8080
CMD ["python", "main.py"]
```

### Performance Considerations

#### Firestore Queries
- Events are queried without limits by default
- Large flush operations process events in user batches
- Firestore transactions prevent race conditions

#### Delivery Concurrency
- SMTP connections are created per delivery
- HTTP webhook requests use connection pooling
- No built-in rate limiting (relies on external services)

#### Memory Usage
- Events loaded into memory during aggregation
- Large user event collections may impact memory
- Consider pagination for users with thousands of events

## REST API Endpoints

The service now provides a FastAPI-based REST API for managing undelivered messages, eliminating the need for external CLI tools to configure SMTP credentials.

### Service Modes

The service can run in three modes via the `SERVICE_MODE` environment variable:
- `combined` (default): Both API server and Pub/Sub processor
- `api-only`: Only the REST API server
- `pubsub-only`: Only the Pub/Sub message processor

### API Endpoints

#### 1. List Users (`GET /users`)
Get all users with their subscription and undelivered message counts.

```bash
curl "http://localhost:8080/users?include_empty=false"
```

**Response:**
```json
[
  {
    "user_id": "ntai",
    "subscription_count": 2,
    "undelivered_count": 5,
    "enabled_subscriptions": 2
  }
]
```

#### 2. Get User Messages (`GET /users/{user_id}/messages`)
Get undelivered messages for a specific user (RESTful design).

```bash
# Get all messages for a user
curl "http://localhost:8080/users/ntai/messages"

# Filter by event type and limit
curl "http://localhost:8080/users/ntai/messages?event_type=NOTIFICATION&limit=10"
```

**Response:**
```json
[
  {
    "event_id": "event-123",
    "user_id": "ntai",
    "event_type": "NOTIFICATION",
    "message": "Your submission was processed",
    "sender": "arxiv-system@arxiv.org",
    "subject": "Submission Update",
    "timestamp": "2023-12-01T10:00:00",
    "metadata": {"source": "arxiv-submission"}
  }
]
```

#### 2a. List All Undelivered Messages (`GET /undelivered`)
Get all undelivered messages across all users (admin/monitoring view).

```bash
# Get all undelivered messages (admin view)
curl "http://localhost:8080/undelivered?limit=100&event_type=ALERT"
```

#### 3. Flush Messages (`POST /flush`)
Flush undelivered messages with delivery via SMTP/webhooks.

```bash
# Flush all undelivered messages
curl -X POST "http://localhost:8080/flush" \
  -H "Content-Type: application/json" \
  -d '{"dry_run": false, "force_delivery": false}'

# Flush for specific user
curl -X POST "http://localhost:8080/flush" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "ntai", "dry_run": false}'

# Dry run (no actual delivery)
curl -X POST "http://localhost:8080/flush" \
  -H "Content-Type: application/json" \
  -d '{"dry_run": true}'
```

**Response:**
```json
{
  "users_processed": 15,
  "messages_delivered": 23,
  "messages_failed": 2,
  "events_cleared": 21,
  "errors": ["Failed to deliver to user_xyz: SMTP timeout"],
  "dry_run": false
}
```

#### 4. Get Specific Message (`GET /users/{user_id}/messages/{message_id}`)
Get a specific message for a user.

```bash
curl "http://localhost:8080/users/ntai/messages/event-123"
```

**Response:**
```json
{
  "event_id": "event-123",
  "user_id": "ntai",
  "event_type": "NOTIFICATION",
  "message": "Your submission was processed",
  "sender": "arxiv-system@arxiv.org",
  "subject": "Submission Update",
  "timestamp": "2023-12-01T10:00:00",
  "metadata": {"source": "arxiv-submission"}
}
```

#### 5. Delete Specific Message (`DELETE /users/{user_id}/messages/{message_id}`)
Delete a specific message for a user.

```bash
curl -X DELETE "http://localhost:8080/users/ntai/messages/event-123"
```

**Response:**
```json
{
  "message": "Message deleted successfully",
  "user_id": "ntai",
  "message_id": "event-123"
}
```

#### 5a. Delete User Messages (`DELETE /users/{user_id}/messages`)
Delete all messages for a user, optionally before a timestamp.

```bash
# Delete all messages for a user
curl -X DELETE "http://localhost:8080/users/ntai/messages"

# Delete messages before timestamp
curl -X DELETE "http://localhost:8080/users/ntai/messages?before_timestamp=2023-12-01T00:00:00"
```

#### 5b. Bulk Delete Messages (`DELETE /undelivered`)
Admin endpoint for bulk deletion with various filtering options.

```bash
# Delete specific events by ID
curl -X DELETE "http://localhost:8080/undelivered" \
  -H "Content-Type: application/json" \
  -d '{"event_ids": ["event-123", "event-456"]}'

# Delete all messages for a user (admin operation)
curl -X DELETE "http://localhost:8080/undelivered" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "ntai"}'
```

#### Statistics Endpoint (`GET /undelivered/stats`)
Get comprehensive statistics about undelivered messages.

```bash
curl "http://localhost:8080/undelivered/stats"
```

**Response:**
```json
{
  "total_users_with_undelivered": 15,
  "total_undelivered_events": 47,
  "users_with_counts": {
    "ntai": 5,
    "researcher123": 12
  },
  "events_by_type": {
    "NOTIFICATION": 35,
    "ALERT": 8,
    "WARNING": 4
  }
}
```

### API Client Example

A Python client is provided in `api_client_example.py`:

```python
from api_client_example import MessagingAPIClient

client = MessagingAPIClient("http://localhost:8080")

# RESTful user message operations
messages = client.get_user_messages("ntai", limit=10)
specific_msg = client.get_user_message("ntai", "event-123")
client.delete_user_message("ntai", "event-123")
client.delete_user_messages("ntai")  # Delete all for user

# Flush operations (uses internal SMTP credentials)
result = client.flush_messages(user_id="ntai", dry_run=True)
print(f"Would deliver: {result['users_processed']} users")

# Admin operations
stats = client.get_undelivered_stats()
all_messages = client.list_all_undelivered_messages()
client.delete_messages_bulk(event_ids=["event-1", "event-2"])
```

### Benefits of REST API Approach

1. **No External SMTP Setup**: Flushing uses the service's configured SMTP credentials
2. **Fine-grained Control**: Delete specific events, users, or time ranges
3. **Real-time Operations**: Immediate feedback without batch processing delays
4. **Standard HTTP Interface**: Easy integration with monitoring and automation tools
5. **Structured Responses**: JSON format with detailed error information
6. **Flexible Deployment**: Can run API-only, Pub/Sub-only, or combined modes

### Environment Variables

```env
# Service configuration
SERVICE_MODE=combined  # combined, api-only, pubsub-only
PORT=8080             # API server port (Cloud Run uses this)

# Existing variables for Pub/Sub and Firestore
GCP_PROJECT_ID=arxiv-production
PUBSUB_SUBSCRIPTION_NAME=event-subscription
FIRESTORE_DATABASE_ID=messaging

# SMTP configuration (used by flush operations)
SMTP_SERVER=smtp-relay.gmail.com
SMTP_PORT=465
SMTP_USER=smtp-relay@arxiv.org
SMTP_PASSWORD=your-smtp-password
```

## Subscription Management Endpoints

### Get User Subscriptions (`GET /users/{user_id}/subscriptions`)
Get all subscriptions for a specific user.

```bash
curl "http://localhost:8080/users/ntai/subscriptions"
```

**Response:**
```json
[
  {
    "subscription_id": "ntai-email-1704105600",
    "user_id": "ntai",
    "delivery_method": "EMAIL",
    "aggregation_frequency": "DAILY",
    "aggregation_method": "HTML",
    "delivery_error_strategy": "RETRY",
    "delivery_time": "09:00",
    "timezone": "UTC",
    "email_address": "ntai@arxiv.org",
    "slack_webhook_url": null,
    "enabled": true
  }
]
```

### Create User Subscription (`POST /users/{user_id}/subscriptions`)
Create a new subscription for a user.

```bash
# Create email subscription
curl -X POST "http://localhost:8080/users/ntai/subscriptions" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "ntai",
    "delivery_method": "EMAIL",
    "aggregation_frequency": "DAILY",
    "aggregation_method": "HTML",
    "delivery_time": "09:00",
    "timezone": "UTC",
    "email_address": "ntai@arxiv.org",
    "enabled": true
  }'

# Create Slack subscription
curl -X POST "http://localhost:8080/users/ntai/subscriptions" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "ntai",
    "delivery_method": "SLACK",
    "aggregation_frequency": "IMMEDIATE",
    "slack_webhook_url": "https://hooks.slack.com/triggers/T123/B456/xyz789",
    "enabled": true
  }'
```

### Get Specific Subscription (`GET /users/{user_id}/subscriptions/{subscription_id}`)
Get details of a specific subscription.

```bash
curl "http://localhost:8080/users/ntai/subscriptions/ntai-email-1704105600"
```

### Update Subscription (`PUT /users/{user_id}/subscriptions/{subscription_id}`)
Update a specific subscription (partial updates supported).

```bash
# Update delivery frequency
curl -X PUT "http://localhost:8080/users/ntai/subscriptions/ntai-email-1704105600" \
  -H "Content-Type: application/json" \
  -d '{
    "aggregation_frequency": "WEEKLY",
    "delivery_time": "10:00"
  }'

# Disable subscription
curl -X PUT "http://localhost:8080/users/ntai/subscriptions/ntai-email-1704105600" \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

### Delete Subscription (`DELETE /users/{user_id}/subscriptions/{subscription_id}`)
Delete a specific subscription.

```bash
curl -X DELETE "http://localhost:8080/users/ntai/subscriptions/ntai-email-1704105600"
```

**Response:**
```json
{
  "message": "Subscription deleted successfully",
  "user_id": "ntai",
  "subscription_id": "ntai-email-1704105600"
}
```

### Subscription Field Validation

**Required for Email Subscriptions:**
- `delivery_method`: "EMAIL"
- `email_address`: Valid email address

**Required for Slack Subscriptions:**
- `delivery_method`: "SLACK" 
- `slack_webhook_url`: Valid Slack webhook URL

**Valid Enum Values:**
- `delivery_method`: EMAIL, SLACK
- `aggregation_frequency`: IMMEDIATE, HOURLY, DAILY, WEEKLY
- `aggregation_method`: PLAIN, HTML, MIME
- `delivery_error_strategy`: RETRY, IGNORE

This REST API architecture provides reliable message delivery with strong consistency guarantees while offering modern HTTP-based management capabilities.
