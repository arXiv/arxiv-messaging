# arXiv Messaging Service Specification

## Overview

The arXiv Messaging Service is a cloud-native event aggregation and notification delivery system designed to process publication events and deliver them to users via email or Slack based on their preferences. The service runs on Google Cloud Platform using Cloud Run, Pub/Sub, and Firestore.

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Event Sources │───▶│   Pub/Sub Topic │───▶│   Cloud Run     │
│                 │    │ notification-   │    │ messaging-      │
│ - arXiv Systems │    │ events          │    │ handler         │
│ - Build Systems │    └─────────────────┘    └─────────────────┘
│ - Review System │                                     │
└─────────────────┘                                     │
                                                        ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Delivery      │◀───│   Firestore     │◀───│   Event         │
│   Providers     │    │   Database      │    │   Processor     │
│                 │    │ - Events        │    │                 │
│ - Email (SMTP)  │    │ - User Prefs    │    │ - Aggregation   │
│ - Slack (Webhook)│   └─────────────────┘    │ - Scheduling    │
└─────────────────┘                           └─────────────────┘
```

## Core Components

### 1. Event Processing
- **Event Store**: Persists events and user preferences in Firestore
- **Pub/Sub Processor**: Consumes messages from `notification-events` topic
- **Event Aggregator**: Groups and formats events based on user preferences
- **Scheduled Delivery**: Handles time-based delivery (daily, weekly, hourly)

### 2. Delivery Providers
- **Email Provider**: SMTP-based email delivery with HTML, plain text, and MIME support
- **Slack Provider**: Webhook-based Slack message delivery

### 3. Data Storage
- **Firestore Database**: `messaging` (native mode)
- **Collections**: 
  - `events`: Individual notification events
  - `user_preferences`: User delivery preferences

## Event Schema

Events published to the Pub/Sub topic must follow this JSON schema:

```json
{
  "event_id": "string (unique identifier)",
  "user_id": "string (target user identifier)", 
  "event_type": "string (NOTIFICATION|ALERT|WARNING|INFO)",
  "message": "string (event content)",
  "sender": "string (sender email, must be @arxiv.org domain)",
  "subject": "string (event subject line)",
  "timestamp": "string (ISO 8601 UTC timestamp)",
  "metadata": {
    "source": "string (optional: event source system)",
    "additional_fields": "any (optional: system-specific data)"
  }
}
```

### Example Event
```json
{
  "event_id": "submission-processed-12345",
  "user_id": "author_789",
  "event_type": "NOTIFICATION",
  "message": "Your paper submission has been successfully processed and assigned ID arXiv:2024.01234",
  "sender": "submission-system@arxiv.org",
  "subject": "Submission Processed - arXiv:2024.01234",
  "timestamp": "2025-09-04T18:30:00Z",
  "metadata": {
    "source": "submission-pipeline",
    "paper_id": "arXiv:2024.01234",
    "processing_time": "45s"
  }
}
```

## User Preferences Schema

User preferences are stored in Firestore with this structure:

```json
{
  "user_id": "string (unique user identifier)",
  "delivery_method": "string (email|slack)",
  "aggregation_frequency": "string (immediate|hourly|daily|weekly)",
  "aggregation_method": "string (plain|HTML|MIME)",
  "delivery_time": "string (HH:MM format, null for immediate/hourly)",
  "timezone": "string (timezone identifier, default: UTC)",
  "email_address": "string (required for email delivery)",
  "slack_channel": "string (required for slack delivery)", 
  "slack_webhook_url": "string (required for slack delivery)"
}
```

### Example User Preferences
```yaml
# Email user with daily HTML digest
user_id: "researcher_123"
email_address: "researcher@university.edu"
delivery_method: "email"
aggregation_frequency: "daily"
aggregation_method: "HTML"
delivery_time: "09:00"
timezone: "UTC"

# Slack user with immediate notifications
user_id: "admin_456" 
delivery_method: "slack"
aggregation_frequency: "immediate"
aggregation_method: "plain"
slack_channel: "#arxiv-alerts"
slack_webhook_url: "https://hooks.slack.com/triggers/..."
```

## Delivery Modes

### 1. Immediate Delivery
- **Trigger**: Message received via Pub/Sub
- **Behavior**: Sends raw message content immediately without aggregation
- **Use Case**: Critical alerts, real-time notifications
- **Format**: Original message content passed through unchanged

### 2. Scheduled Aggregation
- **Frequencies**: Hourly, Daily, Weekly
- **Trigger**: Background scheduler (Cloud Run cron job)
- **Behavior**: Groups events by user and time period, formats according to aggregation method
- **Use Case**: Digest emails, summary reports

## Aggregation Methods

### Plain Text
Simple text-based event listing:
```
Event Summary for User researcher_123
Period: 2025-09-04 to 2025-09-04
Total Events: 3

NOTIFICATION (2 events):
• 14:23 - Paper submission accepted
• 16:45 - Review comments available

ALERT (1 events):
• 18:30 - Build pipeline failure
```

### HTML
Formatted HTML table with styling:
```html
<!DOCTYPE html>
<html>
<head><title>Event Summary</title></head>
<body>
<h2>Event Summary for User researcher_123</h2>
<p>Period: 2025-09-04 to 2025-09-04</p>
<p>Total Events: 3</p>
<table border="1">
  <tr><th>Time</th><th>Type</th><th>Subject</th><th>Message</th></tr>
  <tr><td>14:23</td><td>NOTIFICATION</td><td>Submission Update</td><td>Paper submission accepted</td></tr>
</table>
</body>
</html>
```

### MIME Multipart
Email with multiple attachments containing event data:
```
Content-Type: multipart/mixed; boundary="boundary123"
Subject: Event Summary for User researcher_123

--boundary123
Content-Type: text/plain; charset="utf-8"
Content-Disposition: inline; filename="summary.txt"

Event Summary for User researcher_123
Period: 2025-09-04 to 2025-09-04
Total Events: 3

--boundary123
Content-Type: text/plain; charset="utf-8" 
Content-Disposition: inline; filename="notification_events.txt"

NOTIFICATION Events:
14:23 - Paper submission accepted
16:45 - Review comments available
```

## Configuration

### Environment Variables
- `GCP_PROJECT_ID`: Google Cloud Project ID (required)
- `PUBSUB_SUBSCRIPTION_NAME`: Pub/Sub subscription name (default: "notification-events-subscription")
- `FIRESTORE_DATABASE_ID`: Firestore database ID (default: "messaging")
- `PORT`: HTTP server port for health checks (default: 8080)

### SMTP Configuration (for email delivery)
Configured via environment variables or Cloud Secret Manager:
- `SMTP_SERVER`: SMTP server hostname
- `SMTP_PORT`: SMTP server port (587 for TLS, 465 for SSL)
- `SMTP_USER`: SMTP authentication username
- `SMTP_PASS`: SMTP authentication password
- `SMTP_USE_SSL`: Boolean flag for SSL/TLS usage

## API Endpoints

### Health Check
- **Path**: `/` or `/health`
- **Method**: GET
- **Response**: `200 OK` with body `"OK"`
- **Purpose**: Cloud Run health monitoring

## Deployment

### Prerequisites
1. Google Cloud Project with enabled APIs:
   - Cloud Run API
   - Pub/Sub API  
   - Firestore API
   - Container Registry API

2. Firestore database in native mode
3. Pub/Sub topic and subscription configured
4. Docker registry access

### Deployment Steps
```bash
# 1. Set up Firebase/Firestore infrastructure
./setup-firebase.sh

# 2. Build and push Docker image
./build-docker.sh

# 3. Deploy to Cloud Run
./deploy-service.sh
```

### Infrastructure Components
- **Cloud Run Service**: `messaging-handler`
- **Pub/Sub Topic**: `notification-events`
- **Pub/Sub Subscription**: `notification-events-subscription` 
- **Firestore Database**: `messaging` (native mode)
- **Container Registry**: `gcr.io/arxiv-development/messaging-handler`

## Management Tools

### Subscriber Management
```bash
# List subscribers
python manage_subscribers.py list

# Load subscribers from YAML to Firestore
python manage_subscribers.py load

# Download subscribers from Firestore to YAML
python manage_subscribers.py unload

# Sync YAML to Firestore (clear + load)
python manage_subscribers.py sync

# Clear all subscribers from Firestore
python manage_subscribers.py clear
```

### Test Message Sending
```bash
# Send test message with defaults
./send_test_message.py

# Send custom message
./send_test_message.py --user-id researcher_123 --subject "Test Alert" --message "System maintenance scheduled"
```

## Monitoring and Logging

### Structured Logging
All logs are output in JSON format using structured logging:
```json
{
  "event": "Message processed successfully",
  "user_id": "researcher_123",
  "event_type": "NOTIFICATION", 
  "delivery_method": "email",
  "timestamp": "2025-09-04T18:30:00Z",
  "level": "info"
}
```

### Key Metrics to Monitor
- Message processing rate (messages/second)
- Delivery success/failure rates by provider
- Event aggregation processing time
- Firestore read/write operations
- SMTP connection failures
- Slack webhook response times

### Error Handling
- **Pub/Sub Messages**: Failed messages are nacked and retried
- **Delivery Failures**: Logged with structured error information
- **Database Failures**: Service continues but logs errors for investigation
- **SMTP Failures**: Fallback to alternative SMTP configuration if available

## Security Considerations

### Authentication & Authorization
- Uses Google Cloud Application Default Credentials
- Cloud Run service runs with least-privilege service account
- Firestore access restricted to service account
- No public API endpoints (internal ingress only)

### Data Protection  
- All communication over TLS/HTTPS
- Firestore data encrypted at rest and in transit
- SMTP credentials stored in environment variables or Secret Manager
- Webhook URLs treated as sensitive configuration

### Network Security
- Cloud Run configured with internal ingress
- Pub/Sub subscription push endpoint is internal only
- No external dependencies except for email SMTP servers

## Performance Characteristics

### Throughput
- **Immediate delivery**: Sub-second processing for individual events
- **Batch processing**: 100+ events per aggregation cycle
- **Concurrent processing**: Configurable concurrency (default: 1)

### Scalability
- **Auto-scaling**: Cloud Run scales from 1 to 10 instances
- **Memory**: 512MB per instance 
- **CPU**: 1 vCPU per instance
- **Storage**: Firestore scales automatically

### Resource Limits
- **Message size**: 10MB max (Pub/Sub limit)
- **Email attachment size**: 25MB max (SMTP limit)
- **Concurrent connections**: Limited by Cloud Run scaling
- **Firestore operations**: Subject to GCP quotas

## Troubleshooting

### Common Issues
1. **Messages not processing**: Check Pub/Sub subscription and Cloud Run logs
2. **Email delivery failures**: Verify SMTP configuration and credentials
3. **Slack delivery failures**: Validate webhook URLs and network connectivity  
4. **Firestore access errors**: Check service account permissions and database configuration
5. **Service not scaling**: Review Cloud Run configuration and resource limits

### Debugging Commands
```bash
# Check service status
gcloud run services describe messaging-handler --region us-central1

# View recent logs  
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=messaging-handler" --limit=50

# Test Pub/Sub message publishing
gcloud pubsub topics publish notification-events --message='{"event_id":"debug-1","user_id":"test","event_type":"NOTIFICATION","message":"Debug message","sender":"no-reply@arxiv.org","subject":"Debug","timestamp":"2025-09-04T18:30:00Z","metadata":{}}'

# Check Firestore data
python manage_subscribers.py unload --no-yaml
```

## Version History

- **v1.0**: Initial release with basic event processing and email delivery
- **v1.1**: Added Slack webhook support and aggregation methods
- **v1.2**: Implemented immediate delivery bypass and structured logging
- **v1.3**: Added Firestore native database support and management tools
- **v1.4**: Enhanced error handling and monitoring capabilities

---

*This specification covers the complete arXiv Messaging Service implementation as deployed in the `arxiv-development` Google Cloud Project.*