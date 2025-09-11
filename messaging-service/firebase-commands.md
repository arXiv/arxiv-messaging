# Firebase/Firestore gcloud CLI Commands

## Quick Setup (Automated)
```bash
# Run the setup script
./setup-messaging-service.sh
```

## Manual Commands

### 1. Enable APIs
```bash
gcloud services enable firestore.googleapis.com
gcloud services enable firebase.googleapis.com  
gcloud services enable cloudbuild.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable pubsub.googleapis.com
```

### 2. Create Firestore Database
```bash
# Create Firestore Native database
gcloud firestore databases create \
  --location=us-central1 \
  --type=firestore-native \
  --project=arxiv-development

# OR create in Datastore mode (legacy)
gcloud firestore databases create \
  --location=us-central1 \
  --type=datastore-mode \
  --project=arxiv-development
```

### 3. Create Pub/Sub Resources
```bash
# Create topic
gcloud pubsub topics create notification-events

# Create subscription  
gcloud pubsub subscriptions create notification-events-subscription \
  --topic=notification-events \
  --ack-deadline=600 \
  --message-retention-duration=7d
```

### 4. Set Up IAM Permissions
```bash
# Get the default service account
PROJECT_ID="arxiv-development"
SERVICE_ACCOUNT="${PROJECT_ID}@appspot.gserviceaccount.com"

# Grant Firestore access
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/datastore.user"

# Grant Pub/Sub access  
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/pubsub.subscriber"
```

### 5. Create Firestore Indexes (Optional)
```bash
# Create composite indexes for efficient queries
cat > firestore.indexes.json << 'EOF'
{
  "indexes": [
    {
      "collectionGroup": "events",
      "queryScope": "COLLECTION",
      "fields": [
        {"fieldPath": "user_id", "order": "ASCENDING"},
        {"fieldPath": "timestamp", "order": "ASCENDING"}
      ]
    }
  ]
}
EOF

gcloud firestore indexes composite create --file=firestore.indexes.json
```

## Firestore Management Commands

### View Database Info
```bash
gcloud firestore databases describe --database="(default)"
```

### List Collections
```bash
# Using gcloud (limited)
gcloud firestore collections list

# Using Firebase CLI (more features)
firebase firestore:indexes
```

### Export/Import Data
```bash
# Export
gcloud firestore export gs://your-bucket/firestore-backup

# Import  
gcloud firestore import gs://your-bucket/firestore-backup
```

## Pub/Sub Management

### List Topics and Subscriptions
```bash
gcloud pubsub topics list
gcloud pubsub subscriptions list
```

### Test Publishing
```bash
gcloud pubsub topics publish notification-events \
  --message='{"event_id":"test-1","user_id":"test-user","event_type":"notification","message":"Test message","sender":"test@example.com","subject":"Test Subject","timestamp":"2023-12-01T10:00:00Z","metadata":{}}'
```

### Monitor Subscription
```bash
# Pull messages manually
gcloud pubsub subscriptions pull notification-events-subscription \
  --auto-ack \
  --limit=10
```

## Firebase CLI Alternative

### Install Firebase CLI
```bash
npm install -g firebase-tools
firebase login
```

### Initialize Firebase Project
```bash
firebase init firestore
firebase init functions  # if using Cloud Functions
```

### Deploy Security Rules
```bash
firebase deploy --only firestore:rules
```

## Useful Monitoring Commands

### Check Service Status
```bash
gcloud services list --enabled | grep -E "(firestore|firebase|pubsub)"
```

### View Logs
```bash
gcloud logging read "resource.type=gce_instance AND logName=projects/arxiv-development/logs/firestore"
```

### Check Quotas
```bash
gcloud compute project-info describe --format="value(quotas[].limit,quotas[].metric,quotas[].usage)"
```

## Security Rules (Firestore)

Create `firestore.rules`:
```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    // Allow read/write access to events collection
    match /events/{document} {
      allow read, write: if request.auth != null;
    }
    
    // Allow read/write access to user_preferences collection  
    match /user_preferences/{document} {
      allow read, write: if request.auth != null;
    }
  }
}
```

Deploy rules:
```bash
firebase deploy --only firestore:rules
```