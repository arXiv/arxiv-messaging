#!/bin/bash

# Parse SMTP mode argument
SMTP_MODE="${1:-ssl}"  # Default to ssl

case "$SMTP_MODE" in
  "ssl"|"--ssl")
    SMTP_PORT=465
    SMTP_USE_SSL=true
    SMTP_MODE_NAME="SSL"
    ;;
  "starttls"|"tls"|"--starttls"|"--tls")
    SMTP_PORT=587
    SMTP_USE_SSL=false
    SMTP_MODE_NAME="STARTTLS"
    ;;
  *)
    echo "Usage: $0 [ssl|starttls]"
    echo ""
    echo "SMTP modes:"
    echo "  ssl      - Use SSL on port 465 (default)"
    echo "  starttls - Use STARTTLS on port 587"
    echo ""
    echo "Examples:"
    echo "  $0 ssl      # Deploy with SSL"
    echo "  $0 starttls # Deploy with STARTTLS"
    echo "  $0          # Deploy with SSL (default)"
    exit 1
    ;;
esac

echo "🔧 Deploying with SMTP mode: $SMTP_MODE_NAME (port $SMTP_PORT, SSL: $SMTP_USE_SSL)"

# Configuration
PROJECT_ID="arxiv-development"
SERVICE_NAME="messaging-handler"
REGION="us-central1"
IMAGE_TAG="gcr.io/$PROJECT_ID/$SERVICE_NAME:latest"
PUBSUB_NAME=notification-events-subscription
SECRET_NAME="smtp-relay-arxiv-org-app-password"

# Deploy to Cloud Run
echo "Deploying to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
  --image $IMAGE_TAG \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --set-env-vars GCP_PROJECT_ID=$PROJECT_ID,PUBSUB_SUBSCRIPTION_NAME=$PUBSUB_NAME,FIRESTORE_DATABASE_ID=messaging,SMTP_SERVER=smtp-relay.gmail.com,SMTP_PORT=$SMTP_PORT,SMTP_USE_SSL=$SMTP_USE_SSL \
  --set-secrets SMTP_PASSWORD=$SECRET_NAME:latest \
  --memory 512Mi \
  --cpu 1 \
  --min-instances 1 \
  --max-instances 10 \
  --concurrency 1 \
  --ingress internal \
  --vpc-connector projects/arxiv-development/locations/us-central1/connectors/clourrunconnector \
  --vpc-egress all-traffic

echo "✅ Deployment complete!"
echo "📧 SMTP Configuration: $SMTP_MODE_NAME (port $SMTP_PORT, SSL: $SMTP_USE_SSL)"
echo "🔗 Service URL:"
gcloud run services describe $SERVICE_NAME --region $REGION --format 'value(status.url)'