# arXiv Messaging Service Interface

A Python library providing shared components for arXiv's messaging system, including event types, delivery methods, user preferences, and CLI tools for managing subscribers and undelivered messages.

## Overview

This library serves as the common interface between message publishers and the messaging service, providing:

- **Shared data structures** for events, subscriptions, and delivery preferences
- **CLI tools** for subscriber management and message flushing
- **Firebase/Firestore integration** utilities
- **Notification sending** capabilities

## Components

### Data Structures

- **EventType**: NOTIFICATION, ALERT, WARNING, INFO
- **DeliveryMethod**: EMAIL, SLACK
- **AggregationFrequency**: IMMEDIATE, HOURLY, DAILY, WEEKLY
- **AggregationMethod**: PLAIN, HTML, MIME
- **DeliveryErrorStrategy**: RETRY, IGNORE

### Core Classes

- **Event**: Individual message/notification
- **Subscription**: User delivery preferences (replaces UserPreference)
- **UserPreference**: Backward compatibility alias for Subscription

## Message Flushing Architecture

### System Overview

The messaging service runs as a **GCP Cloud Run container** that processes messages through two primary mechanisms:

1. **Real-time processing**: Continuous GCP Pub/Sub message consumption
2. **Batch flushing**: On-demand delivery of accumulated undelivered messages

### Communication Protocols

#### Inbound Messages
- **GCP Pub/Sub**: JSON messages with streaming pull
  - Flow control: max 100 concurrent messages
  - Message format: `{user_id, event_type, message, sender, subject}`
  - Supports both single user and multi-user delivery

#### Outbound Delivery
- **Email**: SMTP/SMTPS protocol
  - Default: `smtp-relay.gmail.com:465` with SSL
  - Configurable SMTP settings via environment variables
  - Supports both SSL (port 465) and STARTTLS
- **Slack**: HTTP/HTTPS webhooks
  - 30-second timeout with `httpx` client
  - JSON payload: `{subject, message, sender}`

#### Data Storage
- **Google Firestore**: Event and subscription persistence
  - Events collection: undelivered messages
  - Subscriptions collection: user delivery preferences

### Message Flushing Process

```
CLI Command → EventStore.flush_undelivered_messages() → Firestore Query → 
User Subscriptions → Event Aggregation → Delivery (SMTP/HTTP) → 
Clear Events → Return Results
```

#### What Gets Flushed
- **Undelivered messages**: All events remaining in Firestore's events collection
- **Failed deliveries**: Events are only cleared after successful delivery
- **User-specific**: Can flush for all users or specific user ID

#### Aggregation Methods
1. **PLAIN**: Text summary with event counts by type
2. **HTML**: Formatted HTML table with CSS styling  
3. **MIME**: Multipart email with separate attachments per event type

#### Message Flow
1. Query undelivered events from Firestore
2. Retrieve user subscription preferences
3. Aggregate events using user's preferred format
4. Deliver via SMTP (email) or HTTP webhook (Slack)
5. Clear successfully delivered events from storage
6. Return detailed flush results and statistics

## CLI Tools

### Subscriber Management

```bash
# Load subscribers from YAML to Firestore
arxiv-manage-subscribers load --yaml-file subscribers.yaml

# List subscribers from YAML
arxiv-manage-subscribers list

# Sync YAML to Firestore (clear + load)
arxiv-manage-subscribers sync

# Clear all subscribers
arxiv-manage-subscribers clear
```

### Undelivered Message Management

```bash
# Show undelivered message statistics
arxiv-manage-subscribers undelivered list --stats-only

# List detailed undelivered messages
arxiv-manage-subscribers undelivered list

# List for specific user
arxiv-manage-subscribers undelivered list --user-id ntai

# Flush all undelivered messages
arxiv-manage-subscribers undelivered flush

# Flush for specific user only
arxiv-manage-subscribers undelivered flush --user-id ntai

# Dry run (show what would be flushed)
arxiv-manage-subscribers undelivered flush --dry-run

# Force flush regardless of aggregation preferences
arxiv-manage-subscribers undelivered flush --force
```

## Cloud Run Deployment

### Architecture
- **Containerized service** using Docker with Python 3.12
- **Health check endpoint** at `:8080/health` for Cloud Run
- **Long-running process** with continuous Pub/Sub message processing
- **Graceful shutdown** handling for SIGTERM/SIGINT

### Environment Configuration
```env
GCP_PROJECT_ID=your-project-id
PUBSUB_SUBSCRIPTION_NAME=event-subscription
FIRESTORE_DATABASE_ID=messaging
SMTP_SERVER=smtp-relay.gmail.com
SMTP_PORT=465
SMTP_USER=smtp-relay@arxiv.org
SMTP_PASSWORD=your-smtp-password
DEFAULT_EMAIL_SENDER=arxiv-messaging@arxiv.org
```

### Deployment Pattern
- Service runs continuously processing Pub/Sub messages
- Message flushing triggered externally via CLI tools
- CLI connects to same Firestore/SMTP/Slack endpoints
- No direct HTTP API for flushing - uses database access pattern

## Installation

```bash
# Install the library
pip install -e /path/to/arxiv_messaging

# Or with Poetry in your project
poetry add arxiv-messaging --path ../arxiv_messaging --develop
```

## Usage Example

```python
from arxiv_messaging import (
    Event, EventType, DeliveryMethod, 
    AggregationFrequency, AggregationMethod,
    Subscription, send_notification
)

# Create an event
event = Event(
    event_id="event-123",
    user_id="researcher-456", 
    event_type=EventType.NOTIFICATION,
    message="Your paper has been accepted",
    sender="arxiv-system@arxiv.org",
    subject="Paper Acceptance"
)

# Send notification
send_notification(
    user_id="researcher-456",
    event_type="NOTIFICATION", 
    message="Your paper has been accepted",
    sender="arxiv-system@arxiv.org"
)
```

## Development

This library uses Poetry for dependency management and follows the shared library pattern to provide common interfaces between arXiv messaging components.
