"""
Firebase/Firestore data loader and unloader using YAML configuration
"""

import os
from typing import List, Dict, Any
from ruamel.yaml import YAML
import structlog
from firebase_admin import credentials, firestore, initialize_app
import firebase_admin
from .event_type import EventType, UserPreference, Subscription, DeliveryMethod, AggregationFrequency, AggregationMethod, DeliveryErrorStrategy

logger = structlog.get_logger(__name__)

class FirebaseLoader:
    """Load/unload user preferences to/from Firestore using YAML configuration"""
    
    def __init__(self, project_id: str, yaml_file: str = "subscribers.yaml", database_id: str = "messaging"):
        """
        Initialize Firebase connection
        
        Args:
            project_id: GCP project ID
            yaml_file: Path to YAML subscribers file
            database_id: Firestore database ID (default: messaging)
        """
        self.project_id = project_id
        self.yaml_file = yaml_file
        self.database_id = database_id
        self.yaml = YAML()
        self.yaml.preserve_quotes = True
        
        # Initialize Firebase if not already done
        if not firebase_admin._apps:
            # Use default credentials (from environment or service account)
            cred = credentials.ApplicationDefault()
            initialize_app(cred, {'projectId': project_id})
        
        # Create client and get database reference
        client = firestore.client()
        if database_id != "(default)":
            # For non-default databases, we need to create a custom client
            from google.cloud.firestore import Client
            self.db = Client(database=database_id)
        else:
            self.db = client
        logger.info("Firebase loader initialized", project_id=project_id, database_id=database_id, yaml_file=yaml_file)
    
    def load_yaml(self) -> List[Dict[str, Any]]:
        """Load subscribers from YAML file"""
        try:
            with open(self.yaml_file, 'r') as file:
                data = self.yaml.load(file)
                subscribers = data.get('subscribers', [])
                logger.info("Loaded subscribers from YAML", count=len(subscribers))
                return subscribers
        except FileNotFoundError:
            logger.error("YAML file not found", file=self.yaml_file)
            return []
        except Exception as e:
            logger.error("Failed to load YAML file", file=self.yaml_file, error=str(e))
            return []
    
    def save_yaml(self, subscribers: List[Dict[str, Any]]):
        """Save subscribers to YAML file"""
        try:
            data = {'subscribers': subscribers}
            with open(self.yaml_file, 'w') as file:
                self.yaml.dump(data, file)
            logger.info("Saved subscribers to YAML", count=len(subscribers))
        except Exception as e:
            logger.error("Failed to save YAML file", file=self.yaml_file, error=str(e))
            raise
    
    def yaml_to_subscription(self, subscriber_data: Dict[str, Any]) -> Subscription:
        """Convert YAML subscriber data to Subscription object"""
        user_id = subscriber_data['user_id']
        delivery_method = subscriber_data['delivery_method']
        
        # Generate subscription_id if not provided
        subscription_id = subscriber_data.get('subscription_id', f"{user_id}-{delivery_method}")
        
        return Subscription(
            subscription_id=subscription_id,
            user_id=user_id,
            email_address=subscriber_data.get('email_address'),
            delivery_method=DeliveryMethod(delivery_method),
            aggregation_frequency=AggregationFrequency(subscriber_data['aggregation_frequency']),
            aggregation_method=AggregationMethod(subscriber_data['aggregation_method']),
            delivery_error_strategy=DeliveryErrorStrategy(subscriber_data.get('delivery_error_strategy', 'retry')),
            delivery_time=subscriber_data.get('delivery_time', '09:00'),
            timezone=subscriber_data.get('timezone', 'UTC'),
            slack_webhook_url=subscriber_data.get('slack_webhook_url'),
            enabled=subscriber_data.get('enabled', True)
        )

    # Backward compatibility method
    def yaml_to_user_preference(self, subscriber_data: Dict[str, Any]) -> UserPreference:
        """Convert YAML subscriber data to UserPreference object (backward compatibility)"""
        return self.yaml_to_subscription(subscriber_data)
    
    def subscription_to_yaml(self, subscription: Subscription) -> Dict[str, Any]:
        """Convert Subscription object to YAML-compatible dict"""
        return {
            'subscription_id': subscription.subscription_id,
            'user_id': subscription.user_id,
            'email_address': subscription.email_address,
            'delivery_method': subscription.delivery_method.value,
            'aggregation_frequency': subscription.aggregation_frequency.value,
            'aggregation_method': subscription.aggregation_method.value,
            'delivery_error_strategy': subscription.delivery_error_strategy.value,
            'delivery_time': subscription.delivery_time,
            'timezone': subscription.timezone,
            'slack_webhook_url': subscription.slack_webhook_url,
            'enabled': subscription.enabled
        }

    # Backward compatibility method
    def user_preference_to_yaml(self, pref: UserPreference) -> Dict[str, Any]:
        """Convert UserPreference object to YAML-compatible dict (backward compatibility)"""
        return self.subscription_to_yaml(pref)
    
    def load_to_firestore(self) -> int:
        """
        Load subscribers from YAML file to Firestore
        
        Returns:
            Number of subscribers loaded
        """
        subscribers = self.load_yaml()
        if not subscribers:
            logger.warning("No subscribers to load")
            return 0
        
        loaded_count = 0
        collection_ref = self.db.collection('subscriptions')
        
        for subscriber_data in subscribers:
            try:
                # Convert to Subscription to validate data
                subscription = self.yaml_to_subscription(subscriber_data)
                
                # Store in new subscriptions collection
                doc_ref = collection_ref.document(subscription.subscription_id)
                doc_ref.set(self.subscription_to_yaml(subscription))
                
                loaded_count += 1
                logger.info("Loaded subscription to Firestore", 
                           subscription_id=subscription.subscription_id,
                           user_id=subscription.user_id, 
                           delivery_method=subscription.delivery_method.value)
                
            except Exception as e:
                logger.error("Failed to load subscriber", 
                           subscriber=subscriber_data.get('user_id', 'unknown'), 
                           error=str(e))
        
        logger.info("Firestore load completed", loaded=loaded_count, total=len(subscribers))
        return loaded_count
    
    def unload_from_firestore(self, save_to_yaml: bool = True) -> List[UserPreference]:
        """
        Unload all user preferences from Firestore
        
        Args:
            save_to_yaml: Whether to save the data to YAML file
            
        Returns:
            List of UserPreference objects
        """
        collection_ref = self.db.collection('user_preferences')
        docs = collection_ref.stream()
        
        preferences = []
        for doc in docs:
            try:
                data = doc.to_dict()
                user_pref = self.yaml_to_user_preference(data)
                preferences.append(user_pref)
                
                logger.info("Unloaded subscriber from Firestore", 
                           user_id=user_pref.user_id,
                           delivery_method=user_pref.delivery_method.value)
                
            except Exception as e:
                logger.error("Failed to parse Firestore document", 
                           doc_id=doc.id, 
                           error=str(e))
        
        if save_to_yaml and preferences:
            # Convert to YAML format and save
            yaml_data = [self.user_preference_to_yaml(pref) for pref in preferences]
            self.save_yaml(yaml_data)
        
        logger.info("Firestore unload completed", unloaded=len(preferences))
        return preferences
    
    def clear_firestore(self) -> int:
        """
        Clear all user preferences from Firestore
        
        Returns:
            Number of documents deleted
        """
        collection_ref = self.db.collection('user_preferences')
        docs = collection_ref.stream()
        
        deleted_count = 0
        for doc in docs:
            doc.reference.delete()
            deleted_count += 1
            logger.info("Deleted subscriber from Firestore", user_id=doc.id)
        
        logger.info("Firestore clear completed", deleted=deleted_count)
        return deleted_count
    
    def sync_yaml_to_firestore(self) -> Dict[str, int]:
        """
        Sync YAML file to Firestore (clear existing and load from YAML)
        
        Returns:
            Dictionary with 'deleted' and 'loaded' counts
        """
        logger.info("Starting YAML to Firestore sync")
        
        deleted_count = self.clear_firestore()
        loaded_count = self.load_to_firestore()
        
        result = {'deleted': deleted_count, 'loaded': loaded_count}
        logger.info("YAML to Firestore sync completed", **result)
        return result