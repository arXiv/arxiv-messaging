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

This database-centric architecture provides reliable message delivery with strong consistency guarantees while avoiding the complexity of distributed service coordination.
