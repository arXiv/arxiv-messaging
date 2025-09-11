# arXiv Messaging Service - Cloud Run Deployment

This service processes Pub/Sub messages and manages event aggregation with email (SMTP) and Slack (webhook) delivery. It also provides a FastAPI REST API for message management.

## Architecture

- **Cloud Run**: Long-running service with combined API server and Pub/Sub processor
- **FastAPI**: REST API for message management and subscription handling
- **Firestore**: Stores events and user subscriptions (replaces user preferences)
- **Pub/Sub**: Message queue for incoming events
- **SMTP**: Real email delivery via smtp-relay.gmail.com
- **Slack**: Real webhook delivery to Slack workflows

## Prerequisites

1. GCP Project with the following APIs enabled:
   - Cloud Run API
   - Cloud Firestore API
   - Cloud Pub/Sub API
   - Container Registry API

2. Local development tools:
   - Docker
   - Poetry (for local development)
   - Google Cloud SDK

3. Authentication:
   ```bash
   gcloud auth login
   gcloud config set project YOUR_PROJECT_ID
   gcloud auth configure-docker
   ```

4. Create Pub/Sub topic and subscription:
   ```bash
   gcloud pubsub topics create notification-events
   gcloud pubsub subscriptions create notification-events-subscription --topic=notification-events
   ```

## Deployment

### Complete Setup Process

The messaging service includes a comprehensive setup script that creates all required GCP resources:

#### Step 1: Initial Project Setup

```bash
# Set your target environment
export GCP_PROJECT_ID=arxiv-development  # or arxiv-stage, arxiv-production

# Run the complete setup script
./setup-messaging-service.sh
```

**What the setup script creates:**
- ✅ **APIs enabled**: Firestore, Cloud Run, Pub/Sub, Secret Manager, VPC Access
- ✅ **Firestore database** with composite indexes for efficient queries
- ✅ **Pub/Sub topic** (`notification-events`) and subscription (`notification-events-subscription`)
- ✅ **Dedicated service account** (`messaging-service@{project}.iam.gserviceaccount.com`)
- ✅ **IAM permissions** (Firestore User, Pub/Sub Subscriber, Secret Manager Access)
- ✅ **VPC connector** (`clourrunconnector`) for Cloud Run networking
- ✅ **SMTP secret placeholder** in Secret Manager

#### Step 2: Configure SMTP Password (Required)

```bash
# Update the SMTP secret with your real password
echo 'YOUR_REAL_SMTP_PASSWORD' | gcloud secrets versions add smtp-relay-arxiv-org-app-password --data-file=-
```

**Note**: The SMTP password should be an **App Password** from your Gmail/Google Workspace account, not your regular password.

#### Step 3: Deploy the Service

```bash
# Deploy to specific environments using convenience targets
make deploy-dev      # Deploy to arxiv-development
make deploy-staging  # Deploy to arxiv-stage
make deploy-prod     # Deploy to arxiv-production

# Or set environment variable and deploy
export GCP_PROJECT_ID=your-target-project
make deploy
```

### Multi-Environment Setup

The service supports deployment to multiple environments with a single codebase:

```bash
# Development Environment
export GCP_PROJECT_ID=arxiv-development
./setup-messaging-service.sh
make deploy-dev

# Staging Environment  
export GCP_PROJECT_ID=arxiv-stage
./setup-messaging-service.sh
make deploy-staging

# Production Environment
export GCP_PROJECT_ID=arxiv-production
./setup-messaging-service.sh
make deploy-prod
```

### Verification Steps

After deployment, verify the setup:

```bash
# Check service health
make proxy                                    # Start authenticated proxy
curl http://localhost:8080/health            # Should return {"status": "healthy"}

# Check API documentation
curl http://localhost:8080/docs              # FastAPI interactive docs

# Test Pub/Sub integration
gcloud pubsub topics publish notification-events --message='{"event_id":"test-1","user_id":"test-user","event_type":"NOTIFICATION","message":"Test message","sender":"no-reply@arxiv.org","subject":"Test Subject","timestamp":"2025-09-10T10:00:00Z","metadata":{}}'
```

## Environment Variables

**Core Configuration:**
- `GCP_PROJECT_ID`: Target GCP project (arxiv-development, arxiv-stage, arxiv-production)
- `PUBSUB_SUBSCRIPTION_NAME`: Pub/Sub subscription name (default: notification-events-subscription)
- `FIRESTORE_DATABASE_ID`: Firestore database ID (default: messaging)
- `SERVICE_MODE`: Service mode (combined, api-only, pubsub-only)

**SMTP Configuration (Production):**
- `SMTP_SERVER`: SMTP server hostname (default: smtp-relay.gmail.com)
- `SMTP_PORT`: SMTP server port (default: 465)
- `SMTP_USER`: SMTP username for authentication (default: smtp-relay@arxiv.org)
- `SMTP_PASSWORD`: SMTP password from Google Secret Manager (secret: smtp-relay-arxiv-org-app-password)
- `SMTP_USE_SSL`: Whether to use SSL/TLS (default: true)
- `DEFAULT_EMAIL_SENDER`: Default sender email address (default: arxiv-messaging@arxiv.org)

## Message Format

Send messages to the Pub/Sub topic with this JSON format:
```json
{
  "event_id": "unique-event-id",
  "user_id": "user123",
  "event_type": "notification",
  "message": "Your submission was processed",
  "sender": "arxiv-system@example.com",
  "subject": "arXiv Submission Update",
  "timestamp": "2023-12-01T10:00:00Z",
  "metadata": {
    "source": "arxiv-submission"
  }
}
```

## User Subscriptions

Manage user subscriptions via REST API or Firestore console:

**Email Subscription (via API):**
```bash
curl -X POST "http://localhost:8080/users/user123/subscriptions" \
  -H "Content-Type: application/json" \
  -d '{
    "delivery_method": "email",
    "aggregation_frequency": "daily",
    "aggregation_method": "HTML",
    "delivery_time": "09:00",
    "timezone": "UTC",
    "email_address": "user@example.com",
    "delivery_error_strategy": "retry",
    "aggregated_message_subject": "Daily arXiv Updates"
  }'
```

**Slack Subscription (via API):**
```bash
curl -X POST "http://localhost:8080/users/user456/subscriptions" \
  -H "Content-Type: application/json" \
  -d '{
    "delivery_method": "slack",
    "aggregation_frequency": "immediate", 
    "aggregation_method": "plain",
    "timezone": "UTC",
    "slack_webhook_url": "https://hooks.slack.com/triggers/YOUR_WORKSPACE/TRIGGER_ID/SECRET",
    "delivery_error_strategy": "ignore"
  }'
```

## Aggregation Frequencies

- **`"immediate"`**: Send events as they arrive
- **`"hourly"`**: Send aggregated events every hour (at :00 minutes)
- **`"daily"`**: Send daily summaries at 09:00
- **`"weekly"`**: Send weekly summaries on Monday at 09:00

## Aggregation Methods

Each user preference can specify how messages should be formatted:

- **`"plain"`**: Simple text format (default)
- **`"html"`**: Rich HTML table format with styling
- **`"mime"`**: MIME multipart format with separate attachments per event type

### Recommended combinations:
- **Email + HTML**: Professional tables for email clients
- **Email + MIME**: Separate attachments for each event type
- **Slack + plain**: Simple text format for Slack channels
- **Slack + HTML**: Rich formatting (if Slack supports HTML)

## Slack Webhook Setup

1. **Create a Slack Workflow:**
   - Go to your Slack workspace settings
   - Navigate to "Automation" → "Workflow Builder"
   - Create a new workflow with a webhook trigger

2. **Configure Webhook Trigger:**
   - Add a webhook trigger to your workflow
   - The webhook will receive a JSON payload with:
     ```json
     {
       "subject": "Event Subject",
       "message": "Event content/aggregated message"
     }
     ```

3. **Add Workflow Actions:**
   - Add "Send a message" action
   - Use variables from the webhook payload:
     - **Channel**: Choose your target channel (e.g., `#notifications`)
     - **Message**: Use both `{{subject}}` and `{{message}}` variables

4. **Get Webhook URL:**
   - Publish your workflow
   - Copy the webhook URL (format: `https://hooks.slack.com/triggers/...`)
   - Add this URL to your user preference as `slack_webhook_url`

5. **Test the Webhook:**
   ```bash
   curl -X POST -H "Content-Type: application/json" \
        -d '{"subject": "Test Subject", "message": "Test message"}' \
        YOUR_WEBHOOK_URL
   ```

## API Access

### Local Development with Authenticated Proxy

```bash
# Start authenticated proxy
make proxy

# Access API endpoints
curl http://localhost:8080/health
curl http://localhost:8080/docs  # Interactive API documentation
curl http://localhost:8080/users  # List users with message counts
```

### Production API Access

```bash
# Get identity token
TOKEN=$(gcloud auth print-identity-token)
SERVICE_URL=$(gcloud run services describe messaging-handler --region=us-central1 --format='value(status.url)')

# Make authenticated requests
curl -H "Authorization: Bearer $TOKEN" "$SERVICE_URL/health"
```

## Monitoring

- **Cloud Run logs**: `gcloud logs tail --follow "resource.type=cloud_run_revision"`
- **Firestore collections**: `events`, `subscriptions` (replaces user_preferences)
- **Pub/Sub subscription monitoring**: GCP Console
- **API health check**: `/health` endpoint
- **Structured JSON logging** with correlation IDs

## Scaling & Performance

The service is configured with:
- **Min instances**: 1 (always running for continuous processing)
- **Max instances**: 1 (current production setting)
- **Concurrency**: 1 (one request at a time per instance)
- **Memory**: 512Mi
- **CPU**: 1 vCPU
- **Pub/Sub flow control**: Max 100 concurrent messages

## New Features

- ✅ **Real SMTP email delivery** (not stubs)
- ✅ **Real Slack webhook delivery** (not stubs) 
- ✅ **FastAPI REST API** for management
- ✅ **Multi-environment support** (dev/stage/prod)
- ✅ **Subscription management** (replaces user preferences)
- ✅ **Custom aggregated subjects** per subscription
- ✅ **Delivery error strategies** (retry/ignore)
- ✅ **Authenticated proxy** for local development
- ✅ **Message flushing API** for undelivered messages