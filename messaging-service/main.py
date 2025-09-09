import os
import logging
import signal
import sys
import threading
import asyncio
import structlog
import uvicorn
from src.message_server import EventAggregationSystem
from src.api import app

# Configure structured JSON logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logging.basicConfig(
    format="%(message)s",
    stream=None,
    level=logging.INFO,
)

logger = structlog.get_logger(__name__)

def start_pubsub_processor(project_id: str, subscription_name: str, database_id: str):
    """Start the Pub/Sub message processor in a separate thread"""
    try:
        logger.info("Starting Pub/Sub processor", 
                   project_id=project_id,
                   subscription_name=subscription_name,
                   database_id=database_id)
        
        system = EventAggregationSystem(project_id, subscription_name, database_id)
        system.start()  # This will block
        
    except Exception as e:
        logger.error("Pub/Sub processor failed", error=str(e))
        sys.exit(1)

def start_api_server(port: int):
    """Start the FastAPI server"""
    try:
        logger.info("Starting FastAPI server", port=port)
        
        # Configure uvicorn
        config = uvicorn.Config(
            app=app,
            host="0.0.0.0", 
            port=port,
            log_config=None,  # Use our structured logging
            access_log=False   # Disable uvicorn access logs
        )
        
        server = uvicorn.Server(config)
        
        # Run the server
        asyncio.run(server.serve())
        
    except Exception as e:
        logger.error("API server failed", error=str(e))
        sys.exit(1)

def signal_handler(signum, _frame):
    """Handle shutdown signals gracefully"""
    logger.info("Received shutdown signal", signal=signum)
    sys.exit(0)

def main():
    """Main entry point for Cloud Run - runs both API and Pub/Sub processor"""
    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Get configuration from environment variables
    project_id = os.getenv('GCP_PROJECT_ID')
    subscription_name = os.getenv('PUBSUB_SUBSCRIPTION_NAME', 'event-subscription')
    database_id = os.getenv('FIRESTORE_DATABASE_ID', 'messaging')
    api_port = int(os.getenv('PORT', 8080))  # Cloud Run uses PORT env var
    
    if not project_id:
        logger.error("Missing required environment variable", variable="GCP_PROJECT_ID")
        sys.exit(1)
    
    logger.info("Initializing arXiv Messaging Service", 
               project_id=project_id,
               subscription_name=subscription_name,
               database_id=database_id,
               api_port=api_port)
    
    # Determine service mode
    service_mode = os.getenv('SERVICE_MODE', 'combined')  # combined, api-only, pubsub-only
    
    if service_mode == 'api-only':
        logger.info("Starting in API-only mode")
        start_api_server(api_port)
        
    elif service_mode == 'pubsub-only':
        logger.info("Starting in Pub/Sub-only mode")
        start_pubsub_processor(project_id, subscription_name, database_id)
        
    else:  # combined mode (default)
        logger.info("Starting in combined mode (API + Pub/Sub)")
        
        # Start Pub/Sub processor in background thread
        pubsub_thread = threading.Thread(
            target=start_pubsub_processor,
            args=(project_id, subscription_name, database_id),
            daemon=True
        )
        pubsub_thread.start()
        
        # Start API server in main thread (this will block)
        start_api_server(api_port)

if __name__ == "__main__":
    main()