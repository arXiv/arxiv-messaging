#!/usr/bin/env python3
"""
Flush undelivered messages for a user via the messaging service REST API
"""

import argparse
import json
import os
import subprocess
import sys
import requests
import structlog

def setup_logging():
    """Configure structured logging"""
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

def get_identity_token():
    """Get Google Cloud identity token using gcloud"""
    try:
        result = subprocess.run(
            ['gcloud', 'auth', 'print-identity-token'],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to get identity token: {e.stderr}")

def get_service_url(project_id: str, service_name: str, region: str):
    """Get the Cloud Run service URL"""
    try:
        result = subprocess.run([
            'gcloud', 'run', 'services', 'describe', service_name,
            '--region', region,
            '--project', project_id,
            '--format', 'value(status.url)'
        ], capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to get service URL: {e.stderr}")

def flush_user_messages(service_url: str, token: str, user_id: str, 
                       force_delivery: bool = False, dry_run: bool = False):
    """
    Flush undelivered messages for a user via REST API
    
    Args:
        service_url: The Cloud Run service URL
        token: Google Cloud identity token
        user_id: Target user ID
        force_delivery: Force delivery even if aggregation frequency not met
        dry_run: Just return what would be processed without actually flushing
    """
    logger = structlog.get_logger(__name__)
    
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    
    # Prepare the flush request
    flush_data = {
        'user_id': user_id,
        'force_delivery': force_delivery,
        'dry_run': dry_run
    }
    
    flush_url = f"{service_url.rstrip('/')}/flush"
    
    try:
        logger.info("Flushing messages for user", 
                   user_id=user_id, 
                   force_delivery=force_delivery,
                   dry_run=dry_run,
                   url=flush_url)
        
        response = requests.post(flush_url, headers=headers, json=flush_data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            
            print("✅ Flush operation completed successfully!")
            print(f"   User: {user_id}")
            print(f"   Users processed: {result.get('users_processed', 0)}")
            print(f"   Messages delivered: {result.get('messages_delivered', 0)}")
            print(f"   Messages failed: {result.get('messages_failed', 0)}")
            print(f"   Events cleared: {result.get('events_cleared', 0)}")
            
            if result.get('dry_run', False):
                print("   ⚠️  This was a dry run - no actual messages were sent")
            
            if result.get('errors'):
                print(f"   ❌ Errors: {', '.join(result['errors'])}")
                
            return result
            
        elif response.status_code == 404:
            print(f"❌ User '{user_id}' not found or has no undelivered messages")
            return None
            
        else:
            print(f"❌ API request failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Network error: {e}")
        return None
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return None

def list_user_messages(service_url: str, token: str, user_id: str, limit: int = None):
    """List undelivered messages for a user"""
    logger = structlog.get_logger(__name__)
    
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    
    params = {}
    if limit:
        params['limit'] = limit
    
    list_url = f"{service_url.rstrip('/')}/users/{user_id}/messages"
    
    try:
        logger.info("Listing messages for user", user_id=user_id, url=list_url)
        
        response = requests.get(list_url, headers=headers, params=params, timeout=30)
        
        if response.status_code == 200:
            messages = response.json()
            print(f"📋 Found {len(messages)} undelivered messages for user '{user_id}':")
            
            for i, msg in enumerate(messages, 1):
                print(f"   {i}. {msg['subject']} (ID: {msg['event_id'][:8]}...)")
                print(f"      From: {msg['sender']}")
                print(f"      Type: {msg['event_type']}")
                print(f"      Time: {msg['timestamp']}")
                
            return messages
            
        elif response.status_code == 404:
            print(f"📭 No undelivered messages found for user '{user_id}'")
            return []
            
        else:
            print(f"❌ API request failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Network error: {e}")
        return None
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return None

def main():
    setup_logging()
    
    parser = argparse.ArgumentParser(description='Flush undelivered messages for a user')
    parser.add_argument('--user-id', 
                       required=True,
                       help='Target user ID to flush messages for')
    parser.add_argument('--project-id', 
                       default=os.getenv('GCP_PROJECT_ID', 'arxiv-development'),
                       help='GCP project ID (default: arxiv-development)')
    parser.add_argument('--service-name',
                       default='messaging-handler',
                       help='Cloud Run service name (default: messaging-handler)')
    parser.add_argument('--region',
                       default='us-central1',
                       help='GCP region (default: us-central1)')
    parser.add_argument('--service-url',
                       help='Service URL (if not provided, will be retrieved automatically)')
    parser.add_argument('--force-delivery', 
                       action='store_true',
                       help='Force delivery even if aggregation frequency not met')
    parser.add_argument('--dry-run', 
                       action='store_true',
                       help='Show what would be processed without actually flushing')
    parser.add_argument('--list-only', 
                       action='store_true',
                       help='Only list messages, do not flush')
    parser.add_argument('--limit',
                       type=int,
                       help='Limit number of messages to show when listing')
    
    args = parser.parse_args()
    
    try:
        # Get authentication token
        print("🔐 Getting authentication token...")
        token = get_identity_token()
        
        # Get service URL
        if args.service_url:
            service_url = args.service_url
        else:
            print("🔍 Getting service URL...")
            service_url = get_service_url(args.project_id, args.service_name, args.region)
        
        print(f"🔗 Service URL: {service_url}")
        print()
        
        if args.list_only:
            # Just list messages
            list_user_messages(service_url, token, args.user_id, args.limit)
        else:
            # List messages first, then flush
            print("📋 Checking current messages...")
            messages = list_user_messages(service_url, token, args.user_id, args.limit)
            
            if messages is None:
                sys.exit(1)
            elif len(messages) == 0:
                print("✅ No messages to flush")
                return
                
            print()
            print("🚀 Flushing messages...")
            
            # Flush messages
            result = flush_user_messages(
                service_url=service_url,
                token=token,
                user_id=args.user_id,
                force_delivery=args.force_delivery,
                dry_run=args.dry_run
            )
            
            if result is None:
                sys.exit(1)
                
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()