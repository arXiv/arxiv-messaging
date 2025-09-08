#!/bin/bash

# Full deployment script - builds Docker image and deploys to Cloud Run
echo "Starting full deployment..."

# Build Docker image
echo "Step 1: Building Docker image..."
./build-docker.sh

# Deploy to Cloud Run
echo "Step 2: Deploying to Cloud Run..."
./deploy-service.sh

echo "Full deployment complete!"
