# arXiv Messaging Service - Cloud Run Deployment

This service processes Pub/Sub messages and manages event aggregation with email and Slack delivery (currently stubs).

## Architecture

- **Cloud Run**: Long-running service that listens to Pub/Sub messages
- **Firestore**: Stores events and user preferences
- **Pub/Sub**: Message queue for incoming events
- **Scheduler**: Background thread for daily/weekly aggregations

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
   gcloud pubsub topics create events
   gcloud pubsub subscriptions create event-subscription --topic=events
   ```

## Deployment

1. Update configuration in `deploy.sh`:
   ```bash
   PROJECT_ID="your-actual-project-id"
   ```

2. Build and deploy:
   ```bash
   ./deploy.sh
   ```

## Environment Variables

- `GCP_PROJECT_ID`: Your GCP project ID
- `PUBSUB_SUBSCRIPTION_NAME`: Pub/Sub subscription name (default: event-subscription)

### Email Configuration (Optional):
- `SMTP_SERVER`: SMTP server hostname (default: smtp-relay.gmail.com)
- `SMTP_PORT`: SMTP server port (default: 465)
- `SMTP_USER`: SMTP username for authentication (default: smtp-relay@arxiv.org)
- `SMTP_PASSWORD`: SMTP password for authentication (required for actual email sending)
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

## User Preferences

Add user preferences via Firestore console or programmatically:

**Email User:**
```json
{
  "user_id": "user123",
  "delivery_method": "email",
  "aggregation_frequency": "daily",
  "aggregation_method": "HTML",
  "delivery_time": "09:00",
  "timezone": "UTC",
  "email_address": "user@example.com"
}
```

**Slack User:**
```json
{
  "user_id": "user456", 
  "delivery_method": "slack",
  "aggregation_frequency": "immediate",
  "aggregation_method": "plain",
  "timezone": "UTC",
  "slack_channel": "#notifications",
  "slack_webhook_url": "https://hooks.slack.com/triggers/YOUR_WORKSPACE/TRIGGER_ID/SECRET"
}
```

## Aggregation Frequencies

- **`"immediate"`**: Send events as they arrive
- **`"hourly"`**: Send aggregated events every hour (at :00 minutes)
- **`"daily"`**: Send daily summaries at 09:00
- **`"weekly"`**: Send weekly summaries on Monday at 09:00

## Aggregation Methods

Each user preference can specify how messages should be formatted:

- **`"plain"`**: Simple text format (default)
- **`"HTML"`**: Rich HTML table format with styling
- **`"MIME"`**: MIME multipart format with separate attachments per event type

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

## Monitoring

- Cloud Run logs: `gcloud logs tail --follow "resource.type=cloud_run_revision"`
- Firestore collections: `events`, `user_preferences`
- Pub/Sub subscription monitoring in GCP Console

## Scaling

The service is configured with:
- Min instances: 1 (always running for scheduler)
- Max instances: 10
- Concurrency: 1 (one message at a time per instance)