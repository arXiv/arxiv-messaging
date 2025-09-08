#!/bin/bash

# Configuration
PROJECT_ID="arxiv-development"
SERVICE_NAME="messaging-handler"
IMAGE_TAG="gcr.io/$PROJECT_ID/$SERVICE_NAME:latest"

# Build and push Docker image
echo "Building Docker image..."
docker build -t $IMAGE_TAG .

echo "Pushing image to Google Container Registry..."
docker push $IMAGE_TAG

echo "Docker build and push complete!"
echo "Image: $IMAGE_TAG"