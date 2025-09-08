# arXiv Messaging Service - Client Tools

This directory contains client-side management tools for the arXiv messaging service.

## Files

- **`firebase_loader.py`** - Core library for loading/unloading user preferences to/from Firestore
- **`manage_subscribers.py`** - Command-line tool for managing subscribers
- **`send_notification.py`** - Programmatic notification sending functions
- **`send_test_message.py`** - Utility for sending test messages to Pub/Sub
- **`subscribers.yaml`** - User preferences configuration file
- **`__init__.py`** - Python package initialization

## Usage

### Managing Subscribers

```bash
# From the client directory:
cd client

# List current subscribers in YAML file
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

### Sending Test Messages

```bash
# Send test message with defaults (devnull user)
./send_test_message.py

# Send custom test message to user
./send_test_message.py --user-id ntai --subject "Custom Test" --message "Testing the system"

# Send message to multiple users
./send_test_message.py --user-id "ntai,devnull,help-desk" --subject "Multi-User Test" --message "Testing multiple recipients"

# Send email gateway message (direct email)
./send_test_message.py --email-to "test@example.com" --subject "Gateway Test" --message "Testing email gateway"

# Send with different event type
./send_test_message.py --event-type ALERT --sender "admin@arxiv.org"
```

### Programmatic Notification Sending

```python
# Import the client functions
from client import send_notification
import structlog

# Set up logger
logger = structlog.get_logger(__name__)

# Send single notification
message_id = send_notification(
    user_id="researcher_123",
    subject="Paper Published",
    message="Your paper has been published on arXiv",
    sender="publication-system@arxiv.org",
    event_type="NOTIFICATION",
    metadata={"paper_id": "arXiv:2024.01234"},
    logger=logger
)

# Send notification to multiple users
message_id = send_notification(
    user_id=["researcher_123", "advisor_456", "coauthor_789"],
    subject="Paper Submitted",
    message="The paper has been submitted for review",
    sender="submission-system@arxiv.org",
    event_type="NOTIFICATION",
    metadata={"paper_id": "arXiv:2024.01234", "submission_id": "sub_123"},
    logger=logger
)


# Send email gateway message (direct email without user registration)
message_id = send_notification(
    email_to="external@example.com",
    subject="Direct Email",
    message="This email is sent directly without user registration",
    sender="gateway@arxiv.org",
    event_type="NOTIFICATION",
    logger=logger
)
```

### Command Options

```bash
# Use custom project and database
python manage_subscribers.py --project-id my-project --database-id my-db load

# Use custom YAML file
python manage_subscribers.py --yaml-file my-subscribers.yaml load
```

## Configuration

The tools use the following configuration:

- **Default Project**: `arxiv-development` (or `GCP_PROJECT_ID` env var)
- **Default Database**: `messaging`
- **Default YAML File**: `subscribers.yaml`

## Authentication

The tools use Google Cloud Application Default Credentials. Ensure you're authenticated:

```bash
gcloud auth application-default login
```

## Dependencies

The client tools require the same dependencies as the main service:
- `firebase-admin`
- `ruamel.yaml`
- `structlog`

Install via Poetry from the root directory:
```bash
cd ..
poetry install
```