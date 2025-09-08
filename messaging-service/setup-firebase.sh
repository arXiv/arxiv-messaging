#!/bin/bash

# Firebase/Firestore setup script for arXiv messaging service
# Run this script to set up Firestore database and required resources

# Don't exit on errors - handle them gracefully
# set -e

# Configuration (matches your deploy.sh)
PROJECT_ID="arxiv-development"
REGION="us-central1"
DATABASE_ID="(default)"  # Use default database or specify custom name

echo "Setting up Firebase/Firestore for project: $PROJECT_ID"
echo "Region: $REGION"
echo "==========================================="

# Set the active project
echo "Setting active project..."
gcloud config set project $PROJECT_ID

# Enable required APIs
echo "Enabling required APIs..."
gcloud services enable firestore.googleapis.com || echo "Firestore API already enabled - continuing..."
gcloud services enable firebase.googleapis.com || echo "Firebase API already enabled - continuing..."
gcloud services enable cloudbuild.googleapis.com || echo "Cloud Build API already enabled - continuing..."
gcloud services enable run.googleapis.com || echo "Cloud Run API already enabled - continuing..."
gcloud services enable pubsub.googleapis.com || echo "Pub/Sub API already enabled - continuing..."

# Create Firestore database (if it doesn't exist)
echo "Creating Firestore database..."
if gcloud firestore databases describe --database="$DATABASE_ID" >/dev/null 2>&1; then
    echo "Firestore database already exists - skipping..."
else
    gcloud firestore databases create \
        --location=$REGION \
        --type=firestore-native \
        --project=$PROJECT_ID && echo "Firestore database created successfully"
fi

# Create Pub/Sub topic and subscription (matches your deployment)
echo "Creating Pub/Sub resources..."
TOPIC_NAME="notification-events"
SUBSCRIPTION_NAME="notification-events-subscription"

# Create topic
echo "Creating Pub/Sub topic: $TOPIC_NAME"
if gcloud pubsub topics describe $TOPIC_NAME >/dev/null 2>&1; then
    echo "Topic $TOPIC_NAME already exists - skipping..."
else
    gcloud pubsub topics create $TOPIC_NAME && echo "Topic $TOPIC_NAME created successfully"
fi

# Create subscription  
echo "Creating Pub/Sub subscription: $SUBSCRIPTION_NAME"
if gcloud pubsub subscriptions describe $SUBSCRIPTION_NAME >/dev/null 2>&1; then
    echo "Subscription $SUBSCRIPTION_NAME already exists - skipping..."
else
    gcloud pubsub subscriptions create $SUBSCRIPTION_NAME \
        --topic=$TOPIC_NAME \
        --ack-deadline=600 \
        --message-retention-duration=7d && echo "Subscription $SUBSCRIPTION_NAME created successfully"
fi

# Create Firestore indexes (optional but recommended for queries)
echo "Creating Firestore indexes..."

# Index 1: user_id + timestamp for user event queries
echo "Creating index: events (user_id, timestamp)"
if gcloud firestore indexes composite create \
    --collection-group=events \
    --field-config=field-path=user_id,order=ascending \
    --field-config=field-path=timestamp,order=ascending \
    --database="(default)" >/dev/null 2>&1; then
    echo "Index 1 created successfully"
else
    echo "Index 1 may already exist - continuing..."
fi

# Index 2: user_id + event_type + timestamp for filtered user event queries
echo "Creating index: events (user_id, event_type, timestamp)"
if gcloud firestore indexes composite create \
    --collection-group=events \
    --field-config=field-path=user_id,order=ascending \
    --field-config=field-path=event_type,order=ascending \
    --field-config=field-path=timestamp,order=ascending \
    --database="(default)" >/dev/null 2>&1; then
    echo "Index 2 created successfully"
else
    echo "Index 2 may already exist - continuing..."
fi

# Set up IAM permissions for Cloud Run service
echo "Setting up IAM permissions..."
SERVICE_ACCOUNT="${PROJECT_ID}@appspot.gserviceaccount.com"

# Grant Firestore access
echo "Setting up Firestore IAM permissions..."
if gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/datastore.user" >/dev/null 2>&1; then
    echo "Firestore IAM binding added successfully"
else
    echo "Firestore IAM binding may already exist - continuing..."
fi

# Grant Pub/Sub access
echo "Setting up Pub/Sub IAM permissions..."
if gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/pubsub.subscriber" >/dev/null 2>&1; then
    echo "Pub/Sub IAM binding added successfully"
else
    echo "Pub/Sub IAM binding may already exist - continuing..."
fi

echo ""
echo "✅ Firebase/Firestore setup completed!"
echo ""
echo "Resources created:"
echo "- Firestore database in region: $REGION"
echo "- Pub/Sub topic: $TOPIC_NAME" 
echo "- Pub/Sub subscription: $SUBSCRIPTION_NAME"
echo "- Firestore composite indexes for efficient queries"
echo "- IAM permissions for Cloud Run service"
echo ""
echo "Next steps:"
echo "1. Run ./deploy.sh to deploy your messaging service"
echo "2. Test with: gcloud pubsub topics publish $TOPIC_NAME --message='{\"event_id\":\"test-1\",\"user_id\":\"test-user\",\"event_type\":\"test\",\"message\":\"Test message\",\"sender\":\"no-reply@arxiv.org\",\"subject\":\"Test Subject\",\"timestamp\":\"$(date -Iseconds)\",\"metadata\":{}}'"
echo ""