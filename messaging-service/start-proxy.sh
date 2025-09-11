#!/bin/bash
# Simple wrapper to start the authenticated proxy with default settings

set -e

# Default values (use environment variables with fallbacks)
PROJECT_ID=${GCP_PROJECT_ID:-arxiv-development}
SERVICE_NAME=${SERVICE_NAME:-messaging-handler}
REGION=${REGION:-us-central1}
PORT=${PORT:-8080}

echo "🔧 Starting authenticated proxy for Cloud Run service..."
echo "   Project: $PROJECT_ID"
echo "   Service: $SERVICE_NAME"
echo "   Region: $REGION"
echo "   Local Port: $PORT"
echo ""

# Check if Python script exists
if [ ! -f "auth-proxy.py" ]; then
    echo "❌ Error: auth-proxy.py not found in current directory"
    exit 1
fi

# Check if required tools are available
if ! command -v gcloud &> /dev/null; then
    echo "❌ Error: gcloud CLI not found. Please install Google Cloud SDK."
    exit 1
fi

if ! command -v python3 &> /dev/null; then
    echo "❌ Error: python3 not found. Please install Python 3."
    exit 1
fi

# Check if required Python packages are available
python3 -c "import requests, structlog" 2>/dev/null || {
    echo "⚠️  Warning: Required Python packages not found. Installing..."
    pip3 install requests structlog
}

# Check authentication
echo "🔐 Checking authentication..."
if ! gcloud auth print-identity-token >/dev/null 2>&1; then
    echo "❌ Error: Not authenticated with gcloud. Please run:"
    echo "   gcloud auth login"
    echo "   gcloud config set project $PROJECT_ID"
    exit 1
fi

echo "✅ Authentication verified"
echo ""

# Start the proxy
python3 auth-proxy.py \
    --project-id "$PROJECT_ID" \
    --service-name "$SERVICE_NAME" \
    --region "$REGION" \
    --port "$PORT" \
    "$@"