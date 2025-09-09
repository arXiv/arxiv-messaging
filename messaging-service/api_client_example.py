#!/usr/bin/env python3
"""
Example client for the arXiv Messaging Service REST API
"""

import requests
import json
from datetime import datetime
from typing import Optional, List

class MessagingAPIClient:
    """Client for the arXiv Messaging Service REST API"""
    
    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        
    def health_check(self) -> dict:
        """Check if the API is healthy"""
        response = self.session.get(f"{self.base_url}/health")
        response.raise_for_status()
        return response.json()
        
    def list_users(self, include_empty: bool = False) -> List[dict]:
        """List all users with their subscription and undelivered message counts"""
        params = {'include_empty': include_empty}
        response = self.session.get(f"{self.base_url}/users", params=params)
        response.raise_for_status()
        return response.json()
    
    def get_user_messages(self, 
                         user_id: str, 
                         limit: Optional[int] = None,
                         event_type: Optional[str] = None) -> List[dict]:
        """Get undelivered messages for a specific user"""
        params = {}
        if limit:
            params['limit'] = limit
        if event_type:
            params['event_type'] = event_type
            
        response = self.session.get(f"{self.base_url}/users/{user_id}/messages", params=params)
        response.raise_for_status()
        return response.json()
    
    def list_all_undelivered_messages(self, 
                                     limit: Optional[int] = 100,
                                     event_type: Optional[str] = None) -> List[dict]:
        """List all undelivered messages across all users (admin view)"""
        params = {}
        if limit:
            params['limit'] = limit
        if event_type:
            params['event_type'] = event_type
            
        response = self.session.get(f"{self.base_url}/undelivered", params=params)
        response.raise_for_status()
        return response.json()
    
    def get_undelivered_stats(self) -> dict:
        """Get statistics about undelivered messages"""
        response = self.session.get(f"{self.base_url}/undelivered/stats")
        response.raise_for_status()
        return response.json()
    
    def flush_messages(self, 
                      user_id: Optional[str] = None,
                      force_delivery: bool = False,
                      dry_run: bool = False) -> dict:
        """Flush undelivered messages"""
        payload = {
            'force_delivery': force_delivery,
            'dry_run': dry_run
        }
        if user_id:
            payload['user_id'] = user_id
            
        response = self.session.post(f"{self.base_url}/flush", json=payload)
        response.raise_for_status()
        return response.json()
    
    def get_user_message(self, user_id: str, message_id: str) -> dict:
        """Get a specific message for a user"""
        response = self.session.get(f"{self.base_url}/users/{user_id}/messages/{message_id}")
        response.raise_for_status()
        return response.json()
    
    def delete_user_message(self, user_id: str, message_id: str) -> dict:
        """Delete a specific message for a user"""
        response = self.session.delete(f"{self.base_url}/users/{user_id}/messages/{message_id}")
        response.raise_for_status()
        return response.json()
    
    def delete_user_messages(self, 
                            user_id: str,
                            before_timestamp: Optional[datetime] = None) -> dict:
        """Delete all messages for a user, optionally before a timestamp"""
        params = {}
        if before_timestamp:
            params['before_timestamp'] = before_timestamp.isoformat()
            
        response = self.session.delete(f"{self.base_url}/users/{user_id}/messages", params=params)
        response.raise_for_status()
        return response.json()
    
    def delete_messages_bulk(self, 
                            user_id: Optional[str] = None,
                            event_ids: Optional[List[str]] = None,
                            before_timestamp: Optional[datetime] = None) -> dict:
        """Bulk delete undelivered messages (admin operation)"""
        payload = {}
        if user_id:
            payload['user_id'] = user_id
        if event_ids:
            payload['event_ids'] = event_ids
        if before_timestamp:
            payload['before_timestamp'] = before_timestamp.isoformat()
            
        response = self.session.delete(f"{self.base_url}/undelivered", json=payload)
        response.raise_for_status()
        return response.json()

    # Subscription Management Methods
    
    def get_user_subscriptions(self, user_id: str) -> List[dict]:
        """Get all subscriptions for a user"""
        response = self.session.get(f"{self.base_url}/users/{user_id}/subscriptions")
        response.raise_for_status()
        return response.json()
    
    def create_user_subscription(self, 
                                user_id: str,
                                delivery_method: str,
                                aggregation_frequency: str,
                                email_address: Optional[str] = None,
                                slack_webhook_url: Optional[str] = None,
                                **kwargs) -> dict:
        """Create a new subscription for a user"""
        payload = {
            'user_id': user_id,
            'delivery_method': delivery_method,
            'aggregation_frequency': aggregation_frequency
        }
        
        if email_address:
            payload['email_address'] = email_address
        if slack_webhook_url:
            payload['slack_webhook_url'] = slack_webhook_url
            
        # Add optional parameters
        for key, value in kwargs.items():
            if value is not None:
                payload[key] = value
        
        response = self.session.post(f"{self.base_url}/users/{user_id}/subscriptions", json=payload)
        response.raise_for_status()
        return response.json()
    
    def get_user_subscription(self, user_id: str, subscription_id: str) -> dict:
        """Get a specific subscription for a user"""
        response = self.session.get(f"{self.base_url}/users/{user_id}/subscriptions/{subscription_id}")
        response.raise_for_status()
        return response.json()
    
    def update_user_subscription(self, 
                                user_id: str, 
                                subscription_id: str,
                                **updates) -> dict:
        """Update a specific subscription for a user"""
        # Remove None values
        payload = {k: v for k, v in updates.items() if v is not None}
        
        response = self.session.put(f"{self.base_url}/users/{user_id}/subscriptions/{subscription_id}", json=payload)
        response.raise_for_status()
        return response.json()
    
    def delete_user_subscription(self, user_id: str, subscription_id: str) -> dict:
        """Delete a specific subscription for a user"""
        response = self.session.delete(f"{self.base_url}/users/{user_id}/subscriptions/{subscription_id}")
        response.raise_for_status()
        return response.json()

def main():
    """Example usage of the API client"""
    
    # Initialize client
    client = MessagingAPIClient("http://localhost:8080")
    
    try:
        # 1. Health check
        print("🏥 Health Check:")
        health = client.health_check()
        print(f"   Status: {health.get('status')}")
        print()
        
        # 2. List users
        print("👥 Users with undelivered messages:")
        users = client.list_users()
        for user in users[:5]:  # Show first 5
            print(f"   {user['user_id']}: {user['undelivered_count']} undelivered, "
                  f"{user['enabled_subscriptions']} active subscriptions")
        print(f"   ... and {max(0, len(users) - 5)} more users")
        print()
        
        # 3. Get statistics
        print("📊 Undelivered Message Statistics:")
        stats = client.get_undelivered_stats()
        print(f"   Total users with undelivered: {stats['total_users_with_undelivered']}")
        print(f"   Total undelivered events: {stats['total_undelivered_events']}")
        print("   Events by type:")
        for event_type, count in stats['events_by_type'].items():
            print(f"     {event_type}: {count}")
        print()
        
        # 4. List some undelivered messages (admin view)
        print("📬 Sample Undelivered Messages (Admin View):")
        messages = client.list_all_undelivered_messages(limit=5)
        for msg in messages:
            timestamp = msg['timestamp'][:19] if isinstance(msg['timestamp'], str) else str(msg['timestamp'])[:19]
            print(f"   {msg['event_id'][:12]}... | {msg['user_id'][:15]:15} | "
                  f"{msg['event_type']:12} | {timestamp} | {msg['subject'][:30]}")
        print()
        
        # 5. Get messages for a specific user (if any users exist)
        if users:
            user_id = users[0]['user_id']
            print(f"📋 Messages for user '{user_id}' (RESTful endpoint):")
            user_messages = client.get_user_messages(user_id, limit=3)
            for msg in user_messages:
                print(f"   {msg['event_id'][:12]}... | {msg['event_type']:12} | {msg['subject'][:40]} | {msg['message'][:50]}...")
            print()
            
            # 5a. Get a specific message (if any messages exist)
            if user_messages:
                message_id = user_messages[0]['event_id']
                print(f"📄 Specific message '{message_id[:12]}...' for user '{user_id}':")
                specific_msg = client.get_user_message(user_id, message_id)
                print(f"   Subject: {specific_msg['subject']}")
                print(f"   Sender: {specific_msg['sender']}")
                print(f"   Type: {specific_msg['event_type']}")
                print(f"   Message: {specific_msg['message'][:100]}...")
                print()
        
        # 6. Dry run flush
        print("🔍 Dry Run Flush (what would be processed):")
        dry_run_result = client.flush_messages(dry_run=True)
        print(f"   Would process {dry_run_result['users_processed']} users")
        print(f"   Dry run: {dry_run_result['dry_run']}")
        print()
        
        # 7. Example of flushing for a specific user (dry run)
        if users:
            user_id = users[0]['user_id']
            print(f"🚰 Dry Run Flush for user '{user_id}':")
            user_flush = client.flush_messages(user_id=user_id, dry_run=True)
            print(f"   Would process {user_flush['users_processed']} users")
            print()
        
        print("✅ API client example completed successfully!")
        print()
        print("RESTful API Operations:")
        print("📨 User Messages (RESTful endpoints):")
        print("   messages = client.get_user_messages('ntai')")
        print("   message = client.get_user_message('ntai', 'message-123')")
        print("   client.delete_user_message('ntai', 'message-123')")
        print("   client.delete_user_messages('ntai')  # Delete all")
        print()
        print("🔄 Flush Operations:")
        print("   result = client.flush_messages()  # Flush all")
        print("   result = client.flush_messages(user_id='ntai')  # Flush specific user")
        print("   result = client.flush_messages(force_delivery=True)  # Force flush")
        print()
        print("⚙️  Admin Operations:")
        print("   messages = client.list_all_undelivered_messages()  # All messages")
        print("   client.delete_messages_bulk(event_ids=['msg1', 'msg2'])  # Bulk delete")
        print()
        print("📧 Subscription Management:")
        print("   subs = client.get_user_subscriptions('ntai')  # Get all subscriptions")
        print("   sub = client.create_user_subscription('ntai', 'EMAIL', 'DAILY', email_address='ntai@arxiv.org')")
        print("   sub = client.update_user_subscription('ntai', 'sub-123', enabled=False)")
        print("   client.delete_user_subscription('ntai', 'sub-123')")
        
        # Add subscription management demo if we have users
        if users:
            user_id = users[0]['user_id']
            try:
                print()
                print(f"📧 Subscription Management Demo for user '{user_id}':")
                
                # Get existing subscriptions
                existing_subs = client.get_user_subscriptions(user_id)
                print(f"   Existing subscriptions: {len(existing_subs)}")
                for sub in existing_subs[:2]:  # Show first 2
                    print(f"     {sub['subscription_id'][:20]}... | {sub['delivery_method']:5} | {sub['aggregation_frequency']:8} | {sub['enabled']}")
                
                if existing_subs:
                    # Get details of first subscription
                    first_sub = existing_subs[0]
                    sub_detail = client.get_user_subscription(user_id, first_sub['subscription_id'])
                    print(f"   Subscription details: {sub_detail['delivery_method']} to {sub_detail.get('email_address') or 'Slack'}")
                
            except Exception as e:
                print(f"   Could not demo subscriptions: {e}")
        print()
        
    except requests.exceptions.ConnectionError:
        print("❌ Error: Could not connect to the API server.")
        print("   Make sure the messaging service is running on http://localhost:8080")
        print("   Start it with: python main.py")
        
    except requests.exceptions.HTTPError as e:
        print(f"❌ HTTP Error: {e}")
        print(f"   Response: {e.response.text}")
        
    except Exception as e:
        print(f"❌ Unexpected error: {e}")

if __name__ == "__main__":
    main()