# Makefile for arXiv Messaging Service

# Configuration
PROJECT_ID ?= $(shell echo $${GCP_PROJECT_ID:-arxiv-development})
SERVICE_NAME = messaging-handler
REGION = us-central1
IMAGE_TAG = gcr.io/$(PROJECT_ID)/$(SERVICE_NAME):latest
PUBSUB_NAME = notification-events-subscription
SECRET_NAME = smtp-relay-arxiv-org-app-password
CONTAINER_NAME = $(SERVICE_NAME)-local
LOCAL_PORT = 8080

# SMTP Configuration (can be overridden: make deploy SMTP_MODE=starttls)
SMTP_MODE ?= ssl
ifeq ($(SMTP_MODE),starttls)
    SMTP_PORT = 587
    SMTP_USE_SSL = false
    SMTP_MODE_NAME = STARTTLS
else
    SMTP_PORT = 465
    SMTP_USE_SSL = true
    SMTP_MODE_NAME = SSL
endif

# Environment variables for local development
ENV_VARS = -e GCP_PROJECT_ID=$(PROJECT_ID) \
           -e PUBSUB_SUBSCRIPTION_NAME=$(PUBSUB_NAME) \
           -e FIRESTORE_DATABASE_ID=messaging \
           -e SERVICE_MODE=api-only \
           -e SMTP_SERVER=smtp-relay.gmail.com \
           -e SMTP_PORT=$(SMTP_PORT) \
           -e SMTP_USE_SSL=$(SMTP_USE_SSL)

.PHONY: help build push build-push run stop clean logs shell test deploy proxy test-auth remove-public-access grant-access status-service get-auth-url

help: ## Show this help message
	@echo "arXiv Messaging Service - Build & Deploy"
	@echo "========================================"
	@echo "Current Configuration:"
	@echo "  Project: $(PROJECT_ID)"
	@echo "  Region:  $(REGION)"
	@echo "  Service: $(SERVICE_NAME)"
	@echo ""
	@echo "Environment Variables:"
	@echo "  GCP_PROJECT_ID - Override target project (current: $${GCP_PROJECT_ID:-not set})"
	@echo ""
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

build: ## Build Docker image for Cloud Run (from parent directory)
	@echo "Building Docker image for Cloud Run..."
	docker build -t $(IMAGE_TAG) -f ./Dockerfile .
	@echo "✅ Docker build complete!"
	@echo "📦 Image: $(IMAGE_TAG)"

build-local: ## Build Docker image locally (from current directory)
	@echo "Building Docker image locally..."
	docker build -t $(SERVICE_NAME):local -f ./Dockerfile .

push: ## Push Docker image to Google Container Registry
	@echo "Pushing image to Google Container Registry..."
	docker push $(IMAGE_TAG)
	@echo "✅ Docker push complete!"

build-push: build push ## Build and push Docker image to GCR


run: build ## Build and run Docker container locally
	@echo "Starting container $(CONTAINER_NAME)..."
	@docker stop $(CONTAINER_NAME) 2>/dev/null || true
	@docker rm $(CONTAINER_NAME) 2>/dev/null || true
	docker run -d \
		--name $(CONTAINER_NAME) \
		-p $(LOCAL_PORT):8080 \
		$(ENV_VARS) \
		$(IMAGE_TAG)
	@echo "Container started at http://localhost:$(LOCAL_PORT)"
	@echo "Health check: http://localhost:$(LOCAL_PORT)/health"
	@echo "API docs: http://localhost:$(LOCAL_PORT)/docs"
	@echo "OpenAPI spec: http://localhost:$(LOCAL_PORT)/openapi.json"

stop: ## Stop and remove the running container
	@echo "Stopping container $(CONTAINER_NAME)..."
	@docker stop $(CONTAINER_NAME) 2>/dev/null || echo "Container not running"
	@docker rm $(CONTAINER_NAME) 2>/dev/null || echo "Container not found"

clean: stop ## Stop container and remove image
	@echo "Removing image $(IMAGE_TAG)..."
	@docker rmi $(IMAGE_TAG) 2>/dev/null || echo "Image not found"

logs: ## Show container logs
	@docker logs -f $(CONTAINER_NAME)

shell: ## Open shell in running container
	@docker exec -it $(CONTAINER_NAME) /bin/bash

test: ## Test the running service
	@echo "Testing service endpoints..."
	@curl -s http://localhost:$(LOCAL_PORT)/health || echo "Health check failed"
	@echo ""
	@curl -s -I http://localhost:$(LOCAL_PORT)/openapi.json || echo "OpenAPI endpoint failed"
	@echo ""
	@curl -s -I http://localhost:$(LOCAL_PORT)/docs || echo "Docs endpoint failed"

deploy: build-push ## Build, push and deploy to Cloud Run
	@echo "🔧 Deploying to Cloud Run with SMTP mode: $(SMTP_MODE_NAME) (port $(SMTP_PORT), SSL: $(SMTP_USE_SSL))"
	@echo "📋 Target Project: $(PROJECT_ID)"
	gcloud run deploy $(SERVICE_NAME) \
		--image $(IMAGE_TAG) \
		--platform managed \
		--region $(REGION) \
		--service-account messaging-service@$(PROJECT_ID).iam.gserviceaccount.com \
		--set-env-vars GCP_PROJECT_ID=$(PROJECT_ID),PUBSUB_SUBSCRIPTION_NAME=$(PUBSUB_NAME),FIRESTORE_DATABASE_ID=messaging,SMTP_SERVER=smtp-relay.gmail.com,SMTP_PORT=$(SMTP_PORT),SMTP_USE_SSL=$(SMTP_USE_SSL),SERVICE_MODE=combined \
		--set-secrets SMTP_PASSWORD=$(SECRET_NAME):latest \
		--memory 512Mi \
		--cpu 1 \
		--min-instances 1 \
		--max-instances 1 \
		--concurrency 1 \
		--ingress all \
		--vpc-connector projects/$(PROJECT_ID)/locations/$(REGION)/connectors/clourrunconnector \
		--vpc-egress all-traffic
	@echo "✅ Deployment complete!"
	@echo "📧 SMTP Configuration: $(SMTP_MODE_NAME) (port $(SMTP_PORT), SSL: $(SMTP_USE_SSL))"
	@echo "🔗 Service URL:"
	@gcloud run services describe $(SERVICE_NAME) --region $(REGION) --format 'value(status.url)'

proxy: ## Start authenticated proxy to Cloud Run service on localhost:8080
	@echo "🔗 Starting authenticated proxy to Cloud Run service..."
	@echo "📡 This proxy automatically embeds authentication tokens"
	@echo "🚀 Starting proxy server..."
	./start-proxy.sh

proxy-basic: ## Start basic gcloud proxy (no auto-auth)
	@echo "🔗 Starting basic gcloud proxy to Cloud Run service..."
	@echo "📡 Access endpoints at: http://localhost:8080"
	@echo "   Health: http://localhost:8080/health"
	@echo "   Docs: http://localhost:8080/docs" 
	@echo "   OpenAPI: http://localhost:8080/openapi.json"
	@echo ""
	@echo "⚠️  Note: This proxy does NOT embed auth tokens automatically"
	@echo "Press Ctrl+C to stop the proxy"
	gcloud run services proxy $(SERVICE_NAME) --region=$(REGION) --port=8080

test-auth: ## Test authenticated endpoints with bearer token
	@echo "🔐 Testing authenticated Cloud Run service..."
	@TOKEN=$$(gcloud auth print-identity-token) && \
	SERVICE_URL=$$(gcloud run services describe $(SERVICE_NAME) --region=$(REGION) --format='value(status.url)') && \
	echo "🔗 Service URL: $$SERVICE_URL" && \
	echo "" && \
	echo "Testing /health endpoint:" && \
	curl -s -H "Authorization: Bearer $$TOKEN" $$SERVICE_URL/health || echo "Health check failed" && \
	echo "" && \
	echo "Testing /openapi.json endpoint:" && \
	curl -s -H "Authorization: Bearer $$TOKEN" $$SERVICE_URL/openapi.json | head -c 200 && echo "..." && \
	echo "" && \
	echo "✅ OpenAPI spec available at: $$SERVICE_URL/docs"

remove-public-access: ## Remove allUsers permission (make service private)
	@echo "🔒 Removing public access from Cloud Run service..."
	gcloud run services remove-iam-policy-binding $(SERVICE_NAME) \
		--region=$(REGION) \
		--member="allUsers" \
		--role="roles/run.invoker" || echo "allUsers permission not found or already removed"
	@echo "✅ Service is now private - requires authentication"

grant-access: ## Grant access to a specific user/service account (use: make grant-access MEMBER=user:email@domain.com)
	@if [ -z "$(MEMBER)" ]; then \
		echo "❌ Error: Please specify MEMBER. Examples:"; \
		echo "   make grant-access MEMBER=user:john@example.com"; \
		echo "   make grant-access MEMBER=serviceAccount:service@project.iam.gserviceaccount.com"; \
		exit 1; \
	fi
	@echo "🔑 Granting access to $(MEMBER)..."
	gcloud run services add-iam-policy-binding $(SERVICE_NAME) \
		--region=$(REGION) \
		--member="$(MEMBER)" \
		--role="roles/run.invoker"
	@echo "✅ Access granted to $(MEMBER)"

status-service: ## Check Cloud Run service status and URL
	@echo "📋 Cloud Run Service Status:"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@gcloud run services describe $(SERVICE_NAME) --region=$(REGION) --format="table(metadata.name,status.url,status.conditions[0].status,spec.template.spec.containers[0].image)"
	@echo ""
	@echo "🔗 Service URL:"
	@gcloud run services describe $(SERVICE_NAME) --region=$(REGION) --format='value(status.url)'
	@echo ""
	@echo "🔑 IAM Policy:"
	@gcloud run services get-iam-policy $(SERVICE_NAME) --region=$(REGION) --format="table(bindings[].members[],bindings[].role)" || echo "Failed to get IAM policy"

get-auth-url: ## Get authenticated URL for web browser access
	@echo "🌐 For web browser access, you need to authenticate via gcloud:"
	@echo ""
	@echo "1. First, get your identity token:"
	@echo "   TOKEN=\$$(gcloud auth print-identity-token)"
	@echo ""
	@echo "2. Use curl with the token:"
	@SERVICE_URL=$$(gcloud run services describe $(SERVICE_NAME) --region=$(REGION) --format='value(status.url)') && \
	echo "   curl -H \"Authorization: Bearer \$$TOKEN\" $$SERVICE_URL/docs" && \
	echo "" && \
	echo "3. Or use gcloud to proxy (if proxy works with your setup):" && \
	echo "   gcloud run services proxy $(SERVICE_NAME) --region=$(REGION) --port=8080" && \
	echo "   Then browse to: http://localhost:8080/docs"

# Environment-specific deployment targets
deploy-dev: ## Deploy to arxiv-development
	@echo "🚀 Deploying to development environment..."
	@GCP_PROJECT_ID=arxiv-development $(MAKE) deploy

deploy-staging: ## Deploy to arxiv-stage  
	@echo "🚀 Deploying to staging environment..."
	@GCP_PROJECT_ID=arxiv-stage $(MAKE) deploy

deploy-prod: ## Deploy to arxiv-production
	@echo "🚀 Deploying to production environment..."
	@GCP_PROJECT_ID=arxiv-production $(MAKE) deploy

# Development shortcuts
dev: run ## Alias for run
restart: stop run ## Restart the container
status: ## Show container status
	@docker ps | grep $(CONTAINER_NAME) || echo "Container not running"
