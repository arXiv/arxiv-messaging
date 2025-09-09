#!/bin/bash

# Configuration
PROJECT_ID="arxiv-development"
SERVICE_NAME="messaging-handler"
IMAGE_TAG="gcr.io/$PROJECT_ID/$SERVICE_NAME:latest"

# Build and push Docker image
echo "Building Docker image..."
# Build from parent directory to include arxiv_messaging dependency
docker build -t $IMAGE_TAG -f messaging-service/Dockerfile .

echo "Pushing image to Google Container Registry..."
docker push $IMAGE_TAG

echo "Docker build and push complete!"
echo "Image: $IMAGE_TAG"