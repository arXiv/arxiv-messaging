#!/usr/bin/env python3
"""
Command-line tool to manage subscribers in Firebase using YAML configuration
"""

import argparse
import os
import sys
import structlog
from firebase_loader import FirebaseLoader

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

def main():
    setup_logging()
    logger = structlog.get_logger(__name__)
    
    parser = argparse.ArgumentParser(description='Manage subscribers in Firebase')
    parser.add_argument('--project-id', 
                       default=os.getenv('GCP_PROJECT_ID', 'arxiv-development'),
                       help='GCP project ID (default: arxiv-development)')
    parser.add_argument('--yaml-file', 
                       default='subscribers.yaml',
                       help='YAML file with subscribers (default: subscribers.yaml)')
    parser.add_argument('--database-id',
                       default='messaging',
                       help='Firestore database ID (default: messaging)')
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Load command
    load_parser = subparsers.add_parser('load', help='Load subscribers from YAML to Firestore')
    
    # Unload command  
    unload_parser = subparsers.add_parser('unload', help='Unload subscribers from Firestore to YAML')
    unload_parser.add_argument('--no-yaml', action='store_true', 
                              help='Don\'t save to YAML file')
    
    # Clear command
    clear_parser = subparsers.add_parser('clear', help='Clear all subscribers from Firestore')
    
    # Sync command
    sync_parser = subparsers.add_parser('sync', help='Sync YAML file to Firestore (clear + load)')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List subscribers from YAML file')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    try:
        loader = FirebaseLoader(args.project_id, args.yaml_file, args.database_id)
        
        if args.command == 'load':
            count = loader.load_to_firestore()
            print(f"✅ Loaded {count} subscriptions to Firestore")
            
        elif args.command == 'unload':
            save_yaml = not args.no_yaml
            preferences = loader.unload_from_firestore(save_to_yaml=save_yaml)
            if save_yaml:
                print(f"✅ Unloaded {len(preferences)} subscriptions from Firestore to {args.yaml_file}")
            else:
                print(f"✅ Retrieved {len(preferences)} subscriptions from Firestore")
                
        elif args.command == 'clear':
            count = loader.clear_firestore()
            print(f"✅ Cleared {count} subscriptions from Firestore")
            
        elif args.command == 'sync':
            result = loader.sync_yaml_to_firestore()
            print(f"✅ Sync completed: deleted {result['deleted']}, loaded {result['loaded']} subscriptions")
            
        elif args.command == 'list':
            subscribers = loader.load_yaml()
            if not subscribers:
                print("No subscribers found in YAML file")
            else:
                print(f"Found {len(subscribers)} subscriptions in {args.yaml_file}:")
                print()
                print(f"{'Subscription ID':20} {'User ID':15} {'Delivery':15} {'Frequency':10} {'Method':8} {'Strategy':8} {'Details':20}")
                print("-" * 100)
                
                for sub in subscribers:
                    subscription_id = sub.get('subscription_id', f"{sub['user_id']}-{sub['delivery_method']}")
                    delivery_info = ""
                    if sub.get('email_address'):
                        delivery_info = sub['email_address'][:18]
                    
                    enabled_status = "✓" if sub.get('enabled', True) else "✗"
                    error_strategy = sub.get('delivery_error_strategy', 'retry')[:6]
                    
                    print(f"  {enabled_status} {subscription_id[:18]:18} {sub['user_id']:13} {sub['delivery_method']:13} {sub['aggregation_frequency']:8} {sub['aggregation_method']:6} {error_strategy:6} {delivery_info}")
        
    except Exception as e:
        logger.error("Command failed", command=args.command, error=str(e))
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()