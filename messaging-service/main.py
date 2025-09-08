import os
import logging
import signal
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import structlog
from src.message_server import EventAggregationSystem

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

class HealthCheckHandler(BaseHTTPRequestHandler):
    """Simple health check handler for Cloud Run"""
    def do_GET(self):
        if self.path == '/' or self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'OK')
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        # Suppress default HTTP server logging
        pass

def start_health_server():
    """Start HTTP server for Cloud Run health checks"""
    port = int(os.getenv('PORT', 8080))
    server = HTTPServer(('', port), HealthCheckHandler)
    logger.info("Starting health check server", port=port)
    server.serve_forever()

def signal_handler(signum, _frame):
    """Handle shutdown signals gracefully"""
    logger.info("Received shutdown signal", signal=signum)
    sys.exit(0)

def main():
    """Main entry point for Cloud Run"""
    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Get configuration from environment variables
    project_id = os.getenv('GCP_PROJECT_ID')
    subscription_name = os.getenv('PUBSUB_SUBSCRIPTION_NAME', 'event-subscription')
    database_id = os.getenv('FIRESTORE_DATABASE_ID', 'messaging')
    
    if not project_id:
        logger.error("Missing required environment variable", variable="GCP_PROJECT_ID")
        sys.exit(1)
    
    logger.info("Initializing Event Aggregation System", 
               project_id=project_id,
               subscription_name=subscription_name,
               database_id=database_id)
    
    # Start health check server in background thread
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()
    
    # Initialize the system
    try:
        system = EventAggregationSystem(project_id, subscription_name, database_id)
        
        logger.info("System initialized successfully")
        
        # Start the system (this will block)
        system.start()
        
    except Exception as e:
        logger.error("Failed to start system", error=str(e))
        sys.exit(1)

if __name__ == "__main__":
    main()