# arXiv Messaging Service

A GCP Cloud Run service that processes messaging events via Pub/Sub and delivers notifications through email (SMTP) and Slack (webhooks). The service supports real-time delivery, scheduled aggregation, and on-demand flushing of undelivered messages.

## Quick Start: API-Based Management

The recommended way to interact with the messaging service is through its REST API endpoints.

### Starting the Authenticated Proxy

For local development and testing, use the authenticated proxy to easily access the API:

```bash
# Start the authenticated proxy (auto-embeds tokens)
make proxy

# Access the API at http://localhost:8080
curl http://localhost:8080/health
curl http://localhost:8080/docs  # FastAPI documentation
```

### Essential API Operations

#### 1. List Users and Message Counts

```bash
# Get all users with undelivered messages
curl "http://localhost:8080/users"

# Example response:
[
  {
    "user_id": "ntai", 
    "subscription_count": 2,
    "undelivered_count": 5,
    "enabled_subscriptions": 2
  }
]
```

#### 2. View Undelivered Messages

```bash
# Get messages for a specific user
curl "http://localhost:8080/users/ntai/messages"

# Get all undelivered messages (admin view)
curl "http://localhost:8080/undelivered?limit=50"
```

#### 3. Flush/Deliver Messages

```bash
# Flush all undelivered messages
curl -X POST "http://localhost:8080/flush" \
  -H "Content-Type: application/json" \
  -d '{"dry_run": false}'

# Flush for specific user
curl -X POST "http://localhost:8080/flush" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "ntai", "force_delivery": true}'

# Dry run (preview what would be sent)
curl -X POST "http://localhost:8080/flush" \
  -H "Content-Type: application/json" \
  -d '{"dry_run": true}'
```

#### 4. Manage User Subscriptions

```bash
# Get user's subscriptions
curl "http://localhost:8080/users/ntai/subscriptions"

# Create new subscription
curl -X POST "http://localhost:8080/users/ntai/subscriptions" \
  -H "Content-Type: application/json" \
  -d '{
    "delivery_method": "email",
    "aggregation_frequency": "daily", 
    "email_address": "ntai@arxiv.org",
    "aggregated_message_subject": "Daily arXiv Updates"
  }'

# Update existing subscription
curl -X PUT "http://localhost:8080/users/ntai/subscriptions/sub-123" \
  -H "Content-Type: application/json" \
  -d '{"aggregation_frequency": "immediate"}'
```

## Architecture Overview

### Service Components

1. **PubSubEventProcessor** - Handles incoming Pub/Sub messages
2. **EventStore** - Manages Firestore persistence and undelivered message tracking
3. **DeliveryService** - Routes messages to appropriate delivery providers (Email/Slack)
4. **EventAggregator** - Formats messages using different aggregation methods
5. **FastAPI Server** - Provides REST API for management operations

### Cloud Run Integration

The service runs as a long-running Cloud Run container with:
- **HTTP health endpoint** (`:8080/health`) for Cloud Run health checks
- **FastAPI REST API** (`:8080/docs`) for interactive documentation
- **Continuous Pub/Sub processing** in a background thread
- **Graceful shutdown** handling for container lifecycle

### Service Modes

The service can run in three modes via the `SERVICE_MODE` environment variable:
- `combined` (default): Both API server and Pub/Sub processor
- `api-only`: Only the REST API server
- `pubsub-only`: Only the Pub/Sub message processor

## REST API Reference

### Core Endpoints

#### Users and Messages

- **GET `/users`** - List all users with message counts
- **GET `/users/{user_id}/messages`** - Get user's undelivered messages
- **GET `/undelivered`** - Get all undelivered messages (admin)
- **GET `/undelivered/stats`** - Get undelivered message statistics

#### Message Operations

- **POST `/flush`** - Flush/deliver undelivered messages
- **DELETE `/users/{user_id}/messages`** - Delete user's messages
- **DELETE `/users/{user_id}/messages/{message_id}`** - Delete specific message
- **DELETE `/undelivered`** - Bulk delete messages by criteria

#### Subscription Management

- **GET `/users/{user_id}/subscriptions`** - List user subscriptions
- **POST `/users/{user_id}/subscriptions`** - Create subscription
- **GET `/users/{user_id}/subscriptions/{subscription_id}`** - Get specific subscription
- **PUT `/users/{user_id}/subscriptions/{subscription_id}`** - Update subscription
- **DELETE `/users/{user_id}/subscriptions/{subscription_id}`** - Delete subscription

### API Response Examples

#### Flush Operation Response
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

#### Subscription Response
```json
{
  "subscription_id": "ntai-email-1725975234",
  "user_id": "ntai",
  "delivery_method": "email",
  "aggregation_frequency": "daily",
  "aggregation_method": "plain", 
  "delivery_error_strategy": "retry",
  "delivery_time": "09:00",
  "timezone": "UTC",
  "email_address": "ntai@arxiv.org",
  "slack_webhook_url": null,
  "enabled": true,
  "aggregated_message_subject": "Daily arXiv Updates"
}
```

## Deployment and Configuration

### Environment Variables

**Required:**
```bash
GCP_PROJECT_ID=arxiv-development
PUBSUB_SUBSCRIPTION_NAME=notification-events-subscription
FIRESTORE_DATABASE_ID=messaging
```

**SMTP Configuration:**
```bash
SMTP_SERVER=smtp-relay.gmail.com
SMTP_PORT=465  # 587 for STARTTLS
SMTP_USER=smtp-relay@arxiv.org
SMTP_PASSWORD=your-app-password
SMTP_USE_SSL=true  # false for STARTTLS
DEFAULT_EMAIL_SENDER=no-reply@arxiv.org
```

**Service Configuration:**
```bash
SERVICE_MODE=combined  # combined|api-only|pubsub-only
```

### Docker Deployment

```bash
# Build and deploy to Cloud Run
make deploy

# Run locally for development
make run

# Start authenticated proxy
make proxy
```

### Authentication

The Cloud Run service requires Google Cloud authentication:

```bash
# For local development
gcloud auth login
gcloud config set project arxiv-development

# For production, use service account with:
# - Cloud Run Invoker role
# - Pub/Sub Subscriber role  
# - Firestore User role
```

## Message Processing Flow

### Inbound Processing

1. **Pub/Sub Message** received with user_id(s), event details
2. **User Subscriptions** loaded from Firestore
3. **Immediate Delivery** for subscriptions with `aggregation_frequency: immediate`
4. **Event Storage** for subscriptions with scheduled aggregation (hourly/daily)
5. **Message Acknowledgment** after processing

### Aggregation and Delivery

#### Aggregation Methods
1. **PLAIN** - Text summary with event counts by type
2. **HTML** - Formatted HTML table with CSS styling
3. **MIME** - Multipart email with separate attachments per event type

#### Delivery Providers
- **Email**: SMTP/SMTPS via configurable server
- **Slack**: HTTP webhooks with JSON payload

#### Delivery Error Strategies
- **RETRY**: Keep messages for retry on failure (default)
- **IGNORE**: Discard messages on delivery failure

### Message Flushing

Flushing delivers accumulated undelivered messages:

1. **Query undelivered events** from Firestore
2. **Load user subscriptions** and preferences
3. **Aggregate events** using user's preferred method
4. **Deliver via SMTP/HTTP** based on delivery method
5. **Clear successfully delivered events** (respects retry strategy)
6. **Return detailed results** with statistics

## Monitoring and Observability

### Structured Logging

All operations use structured JSON logging with correlation IDs:

```json
{
  "event": "Undelivered messages flushed successfully",
  "user_id": "ntai",
  "subscription_id": "ntai-email-123", 
  "events_delivered": 5,
  "correlation_id": "flush-ntai-1725975234",
  "timestamp": "2025-09-10T16:00:00Z"
}
```

### Health Monitoring

- **Health Endpoint**: `GET /health` returns service status
- **Metrics**: Available through structured logs
- **Correlation IDs**: Track requests across components

### Error Handling

- **Graceful Failures**: Individual message failures don't stop batch processing
- **Retry Logic**: Respects user delivery error strategy preferences
- **Detailed Error Reporting**: API responses include specific error details

## Performance Considerations

### Firestore Optimization

- **Composite Indexes**: Required for `user_id + timestamp + delivered` queries
- **Query Limits**: Default 1000 events per user for flush operations  
- **Batch Operations**: Uses Firestore batch writes for efficiency

### Delivery Concurrency

- **Pub/Sub Flow Control**: Max 100 concurrent messages
- **SMTP Connection Pooling**: Single connection per flush operation
- **HTTP Timeout**: 30-second timeout for Slack webhooks

### Memory Usage

- **Event Batching**: Processes events in user-based batches
- **Streaming Responses**: Uses iterative content streaming in API
- **Connection Management**: Proper cleanup of network resources

---

## Legacy: Database-Centric Management (CLI)

> **Note**: The database-centric approach using external CLI tools is being phased out in favor of the REST API approach above. This section is maintained for backward compatibility.

### Message Flushing via CLI

The messaging service can also be managed through direct database access using external CLI tools. This pattern requires external tools to configure their own SMTP credentials.

#### Communication Architecture

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
         │                       │                       │
         │ 4. Clear events       │                       │
         ├──────────────────────►│                       │
```

### CLI Tools

The external CLI tools provide direct database access for flushing operations:

#### From messaging-service directory:

```bash
# List undelivered messages
python3 ../tests/flush_messages.py --list-only --user-id ntai

# Flush messages for specific user
python3 ../tests/flush_messages.py --user-id ntai --force-delivery

# Dry run flush
python3 ../tests/flush_messages.py --user-id ntai --dry-run
```

#### From arxiv_messaging library:

```bash
# Show statistics
arxiv-manage-subscribers undelivered list --stats-only

# List detailed undelivered messages  
arxiv-manage-subscribers undelivered list --user-id ntai

# Flush all undelivered messages
arxiv-manage-subscribers undelivered flush

# Flush for specific user
arxiv-manage-subscribers undelivered flush --user-id ntai
```

### Database Access Requirements

CLI tools require:
- **Firestore access** for event and subscription queries
- **SMTP credentials** for email delivery
- **Network access** to Slack webhooks
- **GCP authentication** with appropriate IAM roles

This approach is less secure and harder to maintain than the API-based approach, which centralizes credentials and access control in the Cloud Run service.