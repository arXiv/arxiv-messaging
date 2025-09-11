#!/usr/bin/env python3
"""
Command-line tool to manage subscribers in Firebase using YAML configuration
"""

import argparse
import os
import sys
import json
from datetime import datetime
import structlog
from arxiv_messaging.firebase_loader import FirebaseLoader

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
    import os
    setup_logging()
    logger = structlog.get_logger(__name__)
    
    parser = argparse.ArgumentParser(description='Manage subscribers in Firebase')
    parser.add_argument('--project-id', 
                       default=os.getenv('GCP_PROJECT_ID', 'arxiv-development'),
                       help='GCP project ID (default: from GCP_PROJECT_ID env var or arxiv-development)')
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
    
    # Undelivered messages commands
    undelivered_parser = subparsers.add_parser('undelivered', help='Manage undelivered messages')
    undelivered_subparsers = undelivered_parser.add_subparsers(dest='undelivered_command', help='Undelivered message commands')
    
    # List undelivered messages
    list_undelivered_parser = undelivered_subparsers.add_parser('list', help='List undelivered messages')
    list_undelivered_parser.add_argument('--user-id', help='Filter by specific user ID')
    list_undelivered_parser.add_argument('--stats-only', action='store_true', help='Show only statistics')
    
    # Flush undelivered messages
    flush_undelivered_parser = undelivered_subparsers.add_parser('flush', help='Flush undelivered messages')
    flush_undelivered_parser.add_argument('--user-id', help='Flush for specific user ID only')
    flush_undelivered_parser.add_argument('--force', action='store_true', help='Force delivery regardless of aggregation preferences')
    flush_undelivered_parser.add_argument('--dry-run', action='store_true', help='Show what would be flushed without actually doing it')
    
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
        
        elif args.command == 'undelivered':
            if not args.undelivered_command:
                print("Please specify a subcommand: list or flush")
                sys.exit(1)
            
            # Create EventStore instance to access undelivered messages
            try:
                # Import here to avoid circular imports and path issues
                import sys
                import os
                
                # Add messaging-service to path
                messaging_service_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'messaging-service', 'src')
                if messaging_service_path not in sys.path:
                    sys.path.insert(0, messaging_service_path)
                
                from message_server import EventStore
                event_store = EventStore(args.project_id, args.database_id)
                
                if args.undelivered_command == 'list':
                    if args.stats_only:
                        # Show statistics only
                        stats = event_store.get_undelivered_stats()
                        print("📊 Undelivered Messages Statistics:")
                        print(f"  Total users with undelivered messages: {stats.get('total_users_with_undelivered', 0)}")
                        print(f"  Total undelivered events: {stats.get('total_undelivered_events', 0)}")
                        print()
                        print("  Events by type:")
                        for event_type, count in stats.get('events_by_type', {}).items():
                            print(f"    {event_type}: {count}")
                        print()
                        print("  Users with event counts:")
                        for user_id, count in stats.get('users_with_counts', {}).items():
                            print(f"    {user_id}: {count} events")
                    else:
                        # Show detailed list
                        if args.user_id:
                            events = event_store.get_undelivered_events_by_user(args.user_id)
                            undelivered_events = {args.user_id: events} if events else {}
                        else:
                            undelivered_events = event_store.get_undelivered_events()
                        
                        if not undelivered_events:
                            print("✅ No undelivered messages found")
                        else:
                            print(f"📬 Found undelivered messages for {len(undelivered_events)} users:")
                            print()
                            for user_id, events in undelivered_events.items():
                                print(f"User: {user_id} ({len(events)} events)")
                                print(f"{'Event ID':25} {'Type':12} {'Timestamp':20} {'Subject':30}")
                                print("-" * 90)
                                for event in events[:10]:  # Show first 10 events
                                    timestamp_str = event.timestamp.strftime('%Y-%m-%d %H:%M:%S') if hasattr(event.timestamp, 'strftime') else str(event.timestamp)[:19]
                                    subject = (event.subject or 'No subject')[:28]
                                    print(f"  {event.event_id[:23]:23} {event.event_type.value:10} {timestamp_str:18} {subject}")
                                if len(events) > 10:
                                    print(f"  ... and {len(events) - 10} more events")
                                print()
                
                elif args.undelivered_command == 'flush':
                    if args.dry_run:
                        # Dry run - show what would be flushed
                        if args.user_id:
                            events = event_store.get_undelivered_events_by_user(args.user_id)
                            undelivered_events = {args.user_id: events} if events else {}
                        else:
                            undelivered_events = event_store.get_undelivered_events()
                        
                        if not undelivered_events:
                            print("✅ No undelivered messages to flush")
                        else:
                            print(f"🔍 Dry run - would flush undelivered messages for {len(undelivered_events)} users:")
                            total_events = sum(len(events) for events in undelivered_events.values())
                            print(f"  Total events to flush: {total_events}")
                            for user_id, events in undelivered_events.items():
                                subscriptions = event_store.get_user_subscriptions(user_id)
                                enabled_subs = [s for s in subscriptions if s.enabled]
                                print(f"  {user_id}: {len(events)} events → {len(enabled_subs)} subscriptions")
                    else:
                        # Actually flush messages
                        print("🚀 Starting flush of undelivered messages...")
                        
                        # We need to create DeliveryService and EventAggregator instances
                        # Import messaging service components
                        from message_server import DeliveryService, EventAggregator
                        
                        # Create delivery service (providers are auto-registered in constructor)
                        delivery_service = DeliveryService()
                        
                        # Create aggregator
                        aggregator = EventAggregator(event_store)
                        
                        # Flush messages
                        results = event_store.flush_undelivered_messages(
                            delivery_service=delivery_service,
                            aggregator=aggregator,
                            user_id=args.user_id,
                            force_delivery=args.force
                        )
                        
                        print(f"✅ Flush completed:")
                        print(f"  Users processed: {results['users_processed']}")
                        print(f"  Messages delivered: {results['messages_delivered']}")
                        print(f"  Messages failed: {results['messages_failed']}")
                        print(f"  Events cleared: {results['events_cleared']}")
                        
                        if results['errors']:
                            print(f"⚠️  Errors encountered:")
                            for error in results['errors']:
                                print(f"    {error}")
                
            except ImportError as e:
                print(f"❌ Error: Unable to import messaging service components: {e}")
                print("This command requires the messaging-service to be available.")
                sys.exit(1)
        
    except Exception as e:
        logger.error("Command failed", command=args.command, error=str(e))
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
