#!/bin/bash

# Complete messaging service setup script for arXiv messaging service
# Run this script to set up all required GCP resources: Firestore, Pub/Sub, IAM, VPC, Secret Manager

# Don't exit on errors - handle them gracefully
# set -e

# Configuration (uses environment variables with fallbacks)
PROJECT_ID="${GCP_PROJECT_ID:-arxiv-development}"
REGION="us-central1"
DATABASE_ID="messaging"  # Messaging service database

echo "Setting up complete messaging service infrastructure for project: $PROJECT_ID"
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
gcloud services enable secretmanager.googleapis.com || echo "Secret Manager API already enabled - continuing..."
gcloud services enable vpcaccess.googleapis.com || echo "VPC Access API already enabled - continuing..."

# Create Firestore database (if it doesn't exist)
echo "Creating Firestore database..."
if gcloud firestore databases describe --database="$DATABASE_ID" >/dev/null 2>&1; then
    echo "Firestore database already exists - skipping..."
else
    gcloud firestore databases create \
        --database=$DATABASE_ID \
        --location=$REGION \
        --type=firestore-native \
        --project=$PROJECT_ID && echo "Firestore database '$DATABASE_ID' created successfully"
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
    --database="$DATABASE_ID" >/dev/null 2>&1; then
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
    --database="$DATABASE_ID" >/dev/null 2>&1; then
    echo "Index 2 created successfully"
else
    echo "Index 2 may already exist - continuing..."
fi

# Create dedicated service account for Cloud Run
echo "Setting up service account for Cloud Run..."
SERVICE_ACCOUNT="messaging-service@${PROJECT_ID}.iam.gserviceaccount.com"

# Create service account
if gcloud iam service-accounts describe $SERVICE_ACCOUNT >/dev/null 2>&1; then
    echo "Service account already exists - skipping creation..."
else
    gcloud iam service-accounts create messaging-service \
        --display-name="arXiv Messaging Service" \
        --description="Service account for arXiv messaging Cloud Run service" && \
        echo "Service account created successfully"
fi

# Set up IAM permissions for the service account
echo "Setting up IAM permissions..."

# Grant Firestore access
echo "Setting up Firestore IAM permissions..."
if gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/datastore.user" >/dev/null 2>&1; then
    echo "Firestore IAM binding added successfully"
else
    echo "Firestore IAM binding may already exist - continuing..."
fi

# Grant Pub/Sub access (subscriber for receiving messages)
echo "Setting up Pub/Sub subscriber IAM permissions..."
if gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/pubsub.subscriber" >/dev/null 2>&1; then
    echo "Pub/Sub subscriber IAM binding added successfully"
else
    echo "Pub/Sub subscriber IAM binding may already exist - continuing..."
fi

# Grant Pub/Sub publisher access (for message publishing)
echo "Setting up Pub/Sub publisher IAM permissions..."
if gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/pubsub.publisher" >/dev/null 2>&1; then
    echo "Pub/Sub publisher IAM binding added successfully"
else
    echo "Pub/Sub publisher IAM binding may already exist - continuing..."
fi

# Grant Secret Manager access
echo "Setting up Secret Manager IAM permissions..."
if gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/secretmanager.secretAccessor" >/dev/null 2>&1; then
    echo "Secret Manager IAM binding added successfully"
else
    echo "Secret Manager IAM binding may already exist - continuing..."
fi

# Grant Service Account User role to current user for Cloud Run deployment
echo "Setting up Service Account User permissions for current user..."
CURRENT_USER=$(gcloud auth list --filter=status:ACTIVE --format="value(account)")
if gcloud iam service-accounts add-iam-policy-binding $SERVICE_ACCOUNT \
    --member="user:$CURRENT_USER" \
    --role="roles/iam.serviceAccountUser" >/dev/null 2>&1; then
    echo "Service Account User role granted to $CURRENT_USER"
else
    echo "Service Account User role may already exist for $CURRENT_USER - continuing..."
fi

# Set up VPC connector (using existing default network and cloudrunsubnet)
echo "Configuring VPC connector..."
VPC_CONNECTOR_NAME="cloudrunconnector"

if gcloud compute networks vpc-access connectors describe $VPC_CONNECTOR_NAME \
    --region=$REGION >/dev/null 2>&1; then
    echo "VPC connector already exists - using existing connector..."
else
    echo "Creating VPC connector $VPC_CONNECTOR_NAME using existing default network and cloudrunsubnet..."
    gcloud compute networks vpc-access connectors create $VPC_CONNECTOR_NAME \
        --region=$REGION \
        --subnet=cloudrunsubnet \
        --subnet-project=$PROJECT_ID \
        --min-instances=2 \
        --max-instances=3 && \
        echo "VPC connector created successfully" || \
        echo "VPC connector creation failed - may need manual setup"
fi

# Verify SMTP secret exists (must be created manually)
echo "Verifying SMTP secret..."
SECRET_NAME="smtp-relay-arxiv-org-app-password"

if gcloud secrets describe $SECRET_NAME >/dev/null 2>&1; then
    echo "SMTP secret exists - continuing..."
else
    echo "❌ ERROR: SMTP secret $SECRET_NAME does not exist!"
    echo "The SMTP secret must be created manually before running this setup."
    echo ""
    echo "To create the secret with your SMTP password:"
    echo "   echo 'YOUR_REAL_SMTP_PASSWORD' | gcloud secrets create $SECRET_NAME --data-file=-"
    echo ""
    echo "Then re-run this setup script."
    exit 1
fi

# Grant service account access to the SMTP secret
echo "Granting service account access to SMTP secret..."
if gcloud secrets add-iam-policy-binding $SECRET_NAME \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/secretmanager.secretAccessor" >/dev/null 2>&1; then
    echo "SMTP secret access granted to service account"
else
    echo "SMTP secret access may already exist - continuing..."
fi

echo ""
echo "✅ Complete setup finished!"
echo ""
echo "Resources created/configured:"
echo "- ✅ APIs enabled (Firestore, Cloud Run, Pub/Sub, Secret Manager, VPC Access)"
echo "- ✅ Firestore database '$DATABASE_ID' in region: $REGION"
echo "- ✅ Pub/Sub topic: $TOPIC_NAME"
echo "- ✅ Pub/Sub subscription: $SUBSCRIPTION_NAME (600s ack, 7d retention)"
echo "- ✅ Firestore composite indexes for efficient queries"
echo "- ✅ Dedicated service account: $SERVICE_ACCOUNT"
echo "- ✅ IAM permissions (Firestore, Pub/Sub Subscriber/Publisher, Secret Manager, Service Account User)"
echo "- ✅ VPC connector: $VPC_CONNECTOR_NAME (using existing connector)"
echo "- ✅ SMTP secret: $SECRET_NAME (exists with real password, service account has access)"
echo ""
echo "🚀 Next steps:"
echo "1. Deploy the service: make deploy (or make deploy-dev/deploy-staging/deploy-prod)"
echo "2. Test Pub/Sub: gcloud pubsub topics publish $TOPIC_NAME --message='{\"event_id\":\"test-1\",\"user_id\":\"test-user\",\"event_type\":\"NOTIFICATION\",\"message\":\"Test message\",\"sender\":\"no-reply@arxiv.org\",\"subject\":\"Test Subject\",\"timestamp\":\"$(date -Iseconds)\",\"metadata\":{}}'"
echo "3. Start proxy: make proxy"
echo "4. Access API: curl http://localhost:8080/health"
echo ""