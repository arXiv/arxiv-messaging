#!/usr/bin/env python3
"""
Authenticated proxy server for Cloud Run services
Embeds Google Cloud identity token in all requests automatically
"""

import argparse
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
import json
import structlog

# Configure logging
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

logger = structlog.get_logger(__name__)

class TokenManager:
    """Manages Google Cloud identity tokens with automatic refresh"""
    
    def __init__(self):
        self.token = None
        self.expires_at = None
        self.refresh_lock = threading.Lock()
    
    def get_identity_token(self):
        """Get a fresh Google Cloud identity token"""
        try:
            result = subprocess.run(
                ['gcloud', 'auth', 'print-identity-token'],
                capture_output=True,
                text=True,
                check=True,
                timeout=30
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            raise Exception(f"Failed to get identity token: {e.stderr}")
        except subprocess.TimeoutExpired:
            raise Exception("Timeout getting identity token")
    
    def get_token(self):
        """Get valid token, refreshing if necessary"""
        with self.refresh_lock:
            now = datetime.now()
            
            # Refresh token if it doesn't exist or expires soon (5 min buffer)
            if not self.token or not self.expires_at or now >= (self.expires_at - timedelta(minutes=5)):
                logger.info("Refreshing identity token")
                try:
                    self.token = self.get_identity_token()
                    # Google identity tokens typically last 1 hour
                    self.expires_at = now + timedelta(minutes=55)
                    logger.info("Identity token refreshed", expires_at=self.expires_at.isoformat())
                except Exception as e:
                    logger.error("Failed to refresh token", error=str(e))
                    raise
            
            return self.token

class AuthenticatedProxyHandler(BaseHTTPRequestHandler):
    """HTTP request handler that proxies requests with authentication"""
    
    def __init__(self, token_manager, target_url, *args, **kwargs):
        self.token_manager = token_manager
        self.target_url = target_url.rstrip('/')
        super().__init__(*args, **kwargs)
    
    def log_message(self, format, *args):
        """Override to use structured logging"""
        logger.info("HTTP Request", 
                   method=self.command,
                   path=self.path,
                   client=self.client_address[0])
    
    def do_GET(self):
        self._proxy_request('GET')
    
    def do_POST(self):
        self._proxy_request('POST')
    
    def do_PUT(self):
        self._proxy_request('PUT')
    
    def do_DELETE(self):
        self._proxy_request('DELETE')
    
    def do_PATCH(self):
        self._proxy_request('PATCH')
    
    def do_HEAD(self):
        self._proxy_request('HEAD')
    
    def do_OPTIONS(self):
        self._proxy_request('OPTIONS')
    
    def _proxy_request(self, method):
        """Proxy the request to the target service with authentication"""
        try:
            # Get fresh token
            token = self.token_manager.get_token()
            
            # Build target URL
            target_path = self.path
            if self.path.startswith('/'):
                target_path = self.path[1:]  # Remove leading slash
            full_url = f"{self.target_url}/{target_path}" if target_path else self.target_url
            
            # Read request body if present
            content_length = int(self.headers.get('Content-Length', 0))
            request_body = self.rfile.read(content_length) if content_length > 0 else None
            
            # Prepare headers
            proxy_headers = {}
            for header, value in self.headers.items():
                # Skip headers that should not be forwarded
                if header.lower() not in ['host', 'connection', 'content-length']:
                    proxy_headers[header] = value
            
            # Add authentication header
            proxy_headers['Authorization'] = f'Bearer {token}'
            
            logger.info("Proxying request", 
                       method=method,
                       url=full_url,
                       headers_count=len(proxy_headers),
                       body_size=len(request_body) if request_body else 0)
            
            # Make the request
            response = requests.request(
                method=method,
                url=full_url,
                headers=proxy_headers,
                data=request_body,
                timeout=60,
                stream=True
            )
            
            # Send response status
            self.send_response(response.status_code)
            
            # Forward response headers
            for header, value in response.headers.items():
                # Skip headers that should not be forwarded
                if header.lower() not in ['connection', 'transfer-encoding']:
                    self.send_header(header, value)
            self.end_headers()
            
            # Forward response body
            bytes_written = 0
            try:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        self.wfile.write(chunk)
                        bytes_written += len(chunk)
            except BrokenPipeError:
                # Client disconnected, this is normal
                logger.info("Client disconnected during response",
                           method=method,
                           bytes_sent=bytes_written)
                return
            
            logger.info("Request completed", 
                       method=method,
                       status_code=response.status_code,
                       response_size=bytes_written)
            
        except Exception as e:
            logger.error("Proxy request failed", 
                        method=method,
                        error=str(e),
                        error_type=type(e).__name__)
            
            # Send error response (handle broken pipe gracefully)
            try:
                self.send_error(502, f"Proxy Error: {str(e)}")
            except (BrokenPipeError, ConnectionResetError):
                # Client disconnected, cannot send error response
                logger.info("Cannot send error response, client disconnected", method=method)

def get_service_url(project_id, service_name, region):
    """Get the Cloud Run service URL using gcloud"""
    try:
        result = subprocess.run([
            'gcloud', 'run', 'services', 'describe', service_name,
            '--region', region,
            '--project', project_id,
            '--format', 'value(status.url)'
        ], capture_output=True, text=True, check=True, timeout=30)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to get service URL: {e.stderr}")
    except subprocess.TimeoutExpired:
        raise Exception("Timeout getting service URL")

def create_handler_class(token_manager, target_url):
    """Create a request handler class with injected dependencies"""
    class Handler(AuthenticatedProxyHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(token_manager, target_url, *args, **kwargs)
    return Handler

def main():
    parser = argparse.ArgumentParser(description='Authenticated proxy for Cloud Run services')
    parser.add_argument('--project-id', 
                       default=os.getenv('GCP_PROJECT_ID', 'arxiv-development'),
                       help='GCP project ID (default: arxiv-development)')
    parser.add_argument('--service-name',
                       default='messaging-handler',
                       help='Cloud Run service name (default: messaging-handler)')
    parser.add_argument('--region',
                       default='us-central1',
                       help='GCP region (default: us-central1)')
    parser.add_argument('--port',
                       type=int,
                       default=8080,
                       help='Local proxy port (default: 8080)')
    parser.add_argument('--service-url',
                       help='Service URL (if not provided, will be retrieved automatically)')
    
    args = parser.parse_args()
    
    try:
        # Get service URL
        if args.service_url:
            service_url = args.service_url
        else:
            print("🔍 Getting service URL...")
            service_url = get_service_url(args.project_id, args.service_name, args.region)
        
        print(f"🎯 Target service: {service_url}")
        
        # Initialize token manager
        print("🔐 Initializing authentication...")
        token_manager = TokenManager()
        
        # Test token acquisition
        token_manager.get_token()
        print("✅ Authentication successful")
        
        # Create HTTP server
        handler_class = create_handler_class(token_manager, service_url)
        server = HTTPServer(('localhost', args.port), handler_class)
        
        print(f"🚀 Starting authenticated proxy server...")
        print(f"📡 Local URL: http://localhost:{args.port}")
        print(f"🔗 Proxying to: {service_url}")
        print(f"")
        print(f"Available endpoints:")
        print(f"  Health: http://localhost:{args.port}/health")
        print(f"  API Docs: http://localhost:{args.port}/docs")
        print(f"  OpenAPI: http://localhost:{args.port}/openapi.json")
        print(f"")
        print(f"Press Ctrl+C to stop the proxy")
        print(f"")
        
        # Start server
        server.serve_forever()
        
    except KeyboardInterrupt:
        print("\n👋 Stopping proxy server...")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()