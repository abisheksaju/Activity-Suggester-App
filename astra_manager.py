import os
import uuid
import logging
import json
from typing import Dict, List, Any, Optional, Union
from datetime import datetime
from collections import Counter

from astrapy import DataAPIClient

class AstraManager:
    """
    Manages interactions with Astra DB for persistent storage of
    users, activities, preferences, and feedback.
    Implements the same interface as ChromaManager for compatibility.
    """
    
    def __init__(self, token: Optional[str] = None, api_endpoint: Optional[str] = None):
        """Initialize Astra DB client and collections"""
        self.logger = logging.getLogger('astra_manager')
        
        # Get credentials from environment or parameters
        self.token = token or os.environ.get('ASTRA_TOKEN')
        self.api_endpoint = api_endpoint or os.environ.get('ASTRA_API_ENDPOINT')
        
        if not self.token or not self.api_endpoint:
            raise ValueError("Astra DB token and API endpoint are required")
        
        # Initialize client
        self.client = DataAPIClient(self.token)
        self.db = self.client.get_database_by_api_endpoint(self.api_endpoint)
        
        # Initialize collections
        self._init_collections()
        
        self.logger.info("Astra DB collections initialized")
    
    def _init_collections(self):
        """Initialize collections if they don't exist"""
        # Get existing collections
        existing_collections = self.db.list_collection_names()
        
        # Define collection names
        self.users_collection_name = "users"
        self.activities_collection_name = "activities"
        self.places_collection_name = "places"
        self.feedback_collection_name = "feedback"
        
        # Create collections if they don't exist
        for name in [self.users_collection_name, self.activities_collection_name, 
                    self.places_collection_name, self.feedback_collection_name]:
            if name not in existing_collections:
                try:
                    # Create vector collection if needed (for activities)
                    if name == self.activities_collection_name:
                        # Activities need vector search capability for RAG
                        self.db.create_vector_collection(
                            collection_name=name,
                            embedding_field="vector", 
                            dimension=1024  # Using NV Embed QA model dimension
                        )
                    else:
                        # Regular collection for other data
                        self.db.create_collection(name)
                    self.logger.info(f"Created collection: {name}")
                except Exception as e:
                    self.logger.error(f"Error creating collection {name}: {str(e)}")
    
    # User operations
    def add_or_update_user(self, user_id: str, user_data: Dict[str, Any]) -> bool:
        """
        Add or update a user profile in Astra DB
        
        Args:
            user_id: Unique ID for the user
            user_data: User profile data
            
        Returns:
            bool: Success status
        """
        try:
            # Add metadata
            user_data["metadata"] = {
                "updated_at": datetime.now().isoformat()
            }
            
            # Check if user exists
            existing_user = self.db.get_many(
                collection_name=self.users_collection_name,
                filter={"_id": user_id},
                limit=1
            )
            
            if existing_user and len(existing_user) > 0:
                # Update existing user
                user_data["metadata"]["created_at"] = existing_user[0].get("metadata", {}).get(
                    "created_at", datetime.now().isoformat()
                )
                self.logger.info(f"Updated user {user_id}")
            else:
                # Add created_at timestamp for new user
                user_data["metadata"]["created_at"] = datetime.now().isoformat()
                self.logger.info(f"Added new user {user_id}")
                
                # Initialize preferences
                self._initialize_user_preferences(user_id, user_data)
            
            # Store user with ID
            user_data["_id"] = user_id
            self.db.upsert(
                collection_name=self.users_collection_name,
                document=user_data
            )
            
            return True
        except Exception as e:
            self.logger.error(f"Error adding/updating user: {str(e)}")
            return False
    
    def _initialize_user_preferences(self, user_id: str, user_data: Dict[str, Any]):
        """Initialize user preferences when creating a new user"""
        try:
            # Extract initial interests from user data
            initial_interests = user_data.get("interests", {})
            
            # Create preferences data structure
            preferences = {
                "_id": f"{user_id}_preferences",
                "user_id": user_id,
                "category_preferences": initial_interests,
                "liked_places": [],
                "disliked_places": [],
                "metadata": {
                    "type": "preferences",
                    "user_id": user_id,
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat()
                }
            }
            
            # Store preferences
            self.db.upsert(
                collection_name=self.users_collection_name,
                document=preferences
            )
            
            self.logger.info(f"Initialized preferences for user {user_id}")
        except Exception as e:
            self.logger.error(f"Error initializing user preferences: {str(e)}")
    
    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a user profile from Astra DB
        
        Args:
            user_id: Unique ID for the user
            
        Returns:
            Dict or None: User profile data or None if not found
        """
        try:
            result = self.db.get_many(
                collection_name=self.users_collection_name,
                filter={"_id": user_id},
                limit=1
            )
            
            if result and len(result) > 0:
                return result[0]
            
            return None
        except Exception as e:
            self.logger.error(f"Error getting user: {str(e)}")
            return None
    
    def delete_user(self, user_id: str) -> bool:
        """
        Delete a user profile from Astra DB
        
        Args:
            user_id: Unique ID for the user
            
        Returns:
            bool: Success status
        """
        try:
            # Delete user profile
            self.db.delete(
                collection_name=self.users_collection_name,
                filter={"_id": user_id}
            )
            
            # Delete user preferences
            preferences_id = f"{user_id}_preferences"
            self.db.delete(
                collection_name=self.users_collection_name,
                filter={"_id": preferences_id}
            )
            
            # Delete user feedback
            self._delete_user_feedback(user_id)
            
            # Delete user activities
            self._delete_user_activities(user_id)
            
            self.logger.info(f"Deleted user {user_id}")
            return True
        except Exception as e:
            self.logger.error(f"Error deleting user: {str(e)}")
            return False
    
    def _delete_user_feedback(self, user_id: str):
        """Delete all feedback for a user"""
        try:
            self.db.delete(
                collection_name=self.feedback_collection_name,
                filter={"user_id": user_id}
            )
            self.logger.info(f"Deleted feedback for user {user_id}")
        except Exception as e:
            self.logger.error(f"Error deleting user feedback: {str(e)}")
    
    def _delete_user_activities(self, user_id: str):
        """Delete all activities for a user"""
        try:
            self.db.delete(
                collection_name=self.activities_collection_name,
                filter={"user_id": user_id}
            )
            self.logger.info(f"Deleted activities for user {user_id}")
        except Exception as e:
            self.logger.error(f"Error deleting user activities: {str(e)}")
    
    def get_all_users(self) -> List[Dict[str, Any]]:
        """
        Get all user profiles from Astra DB
        
        Returns:
            List[Dict]: List of user profiles
        """
        try:
            # Get all users (excluding preferences entries)
            result = self.db.get_many(
                collection_name=self.users_collection_name,
                filter={"metadata.type": {"$ne": "preferences"}}
            )
            
            return result if result else []
        except Exception as e:
            self.logger.error(f"Error getting all users: {str(e)}")
            return []
    
    # User preferences operations
    def get_user_preferences(self, user_id: str) -> Dict[str, Any]:
        """
        Get user preferences from Astra DB
        
        Args:
            user_id: Unique ID for the user
            
        Returns:
            Dict: User preferences
        """
        try:
            preferences_id = f"{user_id}_preferences"
            result = self.db.get_many(
                collection_name=self.users_collection_name,
                filter={"_id": preferences_id},
                limit=1
            )
            
            if result and len(result) > 0:
                return result[0]
            
            # Return default preferences if not found
            return {
                "user_id": user_id,
                "category_preferences": {
                    "food": 0.8,
                    "travel": 0.5,
                    "shopping": 0.5,
                    "gaming": 0.5,
                    "news": 0.5,
                    "fitness": 0.7,
                    "cooking": 0.9
                },
                "liked_places": [],
                "disliked_places": []
            }
        except Exception as e:
            self.logger.error(f"Error getting user preferences: {str(e)}")
            # Return default preferences on error
            return {
                "user_id": user_id,
                "category_preferences": {
                    "food": 0.7,
                    "travel": 0.6,
                    "shopping": 0.5,
                    "gaming": 0.5,
                    "news": 0.4
                },
                "liked_places": [],
                "disliked_places": []
            }
    
    def update_preferences_from_feedback(self, feedback_data: Dict[str, Any]):
        """
        Update user preferences based on feedback
        
        Args:
            feedback_data: Feedback data
        """
        try:
            user_id = feedback_data.get("user_id")
            if not user_id:
                self.logger.error("Missing user_id in feedback data")
                return
            
            # Get current preferences
            preferences = self.get_user_preferences(user_id)
            
            # Update category preferences based on feedback type
            category = feedback_data.get("interest_category")
            feedback_type = feedback_data.get("feedback_type")
            
            if category and "category_preferences" in preferences and category in preferences["category_preferences"]:
                current_score = preferences["category_preferences"][category]
                
                if feedback_type == "like":
                    # Increase score for likes
                    preferences["category_preferences"][category] = min(1.0, current_score + 0.1)
                    
                    # Add to liked places for outdoor activities
                    if feedback_data.get("activity_type") == "outdoor":
                        place_data = {
                            "name": feedback_data.get("activity_name", "Unknown"),
                            "type": category,
                            "timestamp": datetime.now().isoformat()
                        }
                        preferences["liked_places"].append(place_data)
                        
                elif feedback_type == "dislike":
                    # Decrease score for dislikes
                    preferences["category_preferences"][category] = max(0.1, current_score - 0.1)
                    
                    # Add to disliked places for outdoor activities
                    if feedback_data.get("activity_type") == "outdoor":
                        place_data = {
                            "name": feedback_data.get("activity_name", "Unknown"),
                            "type": category,
                            "timestamp": datetime.now().isoformat()
                        }
                        preferences["disliked_places"].append(place_data)
                        
                elif feedback_type == "view_details":
                    # Slightly increase score for views
                    preferences["category_preferences"][category] = min(1.0, current_score + 0.05)
            
            # Trim lists if they get too long
            if "liked_places" in preferences and len(preferences["liked_places"]) > 20:
                preferences["liked_places"] = preferences["liked_places"][-20:]
            if "disliked_places" in preferences and len(preferences["disliked_places"]) > 20:
                preferences["disliked_places"] = preferences["disliked_places"][-20:]
            
            # Update preferences metadata
            if "metadata" not in preferences:
                preferences["metadata"] = {}
            
            preferences["metadata"].update({
                "type": "preferences",
                "user_id": user_id,
                "updated_at": datetime.now().isoformat()
            })
            
            # Save updated preferences
            preferences_id = f"{user_id}_preferences"
            preferences["_id"] = preferences_id
            self.db.upsert(
                collection_name=self.users_collection_name,
                document=preferences
            )
            
            self.logger.info(f"Updated preferences for user {user_id}")
        except Exception as e:
            self.logger.error(f"Error updating preferences from feedback: {str(e)}")
    
    # Activity operations
    def add_activity(self, activity_data: Dict[str, Any]) -> bool:
        """
        Add a new activity to Astra DB with vector embedding
        
        Args:
            activity_data: Activity data
            
        Returns:
            bool: Success status
        """
        try:
            activity_id = activity_data.get("id", str(uuid.uuid4()))
            
            # Ensure activity has an ID
            activity_data["_id"] = activity_id
            
            # Add metadata if not present
            if "metadata" not in activity_data:
                activity_data["metadata"] = {}
            
            # Update metadata
            activity_data["metadata"].update({
                "user_id": activity_data.get("user_id", "unknown"),
                "type": activity_data.get("type", "unknown"),
                "timestamp": datetime.now().isoformat()
            })
            
            # Extract text for embedding
            description = activity_data.get("description", "")
            name = activity_data.get("name", "")
            activity_type = activity_data.get("activity_type", "")
            
            # Combine text fields for better embedding context
            text_for_embedding = f"{name} {description} {activity_type}".strip()
            
            # Set the $vector field for Astra DB to generate embedding
            # This uses the built-in NVIDIA embedding on Astra DB
            activity_data["$vector"] = text_for_embedding
            
            # Store the activity
            self.db.upsert(
                collection_name=self.activities_collection_name,
                document=activity_data
            )
            
            self.logger.info(f"Added activity {activity_id}")
            return True
        except Exception as e:
            self.logger.error(f"Error adding activity: {str(e)}")
            return False
    
    def update_activity_image(self, activity_id: str, image_url: str) -> bool:
        """
        Update the image URL for an activity
        
        Args:
            activity_id: Activity ID
            image_url: Image URL
            
        Returns:
            bool: Success status
        """
        try:
            # Get current activity
            result = self.db.get_many(
                collection_name=self.activities_collection_name,
                filter={"_id": activity_id},
                limit=1
            )
            
            if result and len(result) > 0:
                activity_data = result[0]
                
                # Update image URL
                activity_data["image_url"] = image_url
                
                # Store updated activity
                self.db.upsert(
                    collection_name=self.activities_collection_name,
                    document=activity_data
                )
                
                self.logger.info(f"Updated image for activity {activity_id}")
                return True
            
            return False
        except Exception as e:
            self.logger.error(f"Error updating activity image: {str(e)}")
            return False
    
    def get_user_activities(
        self, 
        user_id: str, 
        activity_type: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get activities for a user
        
        Args:
            user_id: User ID
            activity_type: Optional filter by activity type
            limit: Maximum number of activities to return
            
        Returns:
            List[Dict]: List of activities
        """
        try:
            # Build filter
            filter_query = {"metadata.user_id": user_id}
            if activity_type:
                filter_query["metadata.type"] = activity_type
            
            # Query activities
            result = self.db.get_many(
                collection_name=self.activities_collection_name,
                filter=filter_query,
                limit=limit
            )
            
            return result if result else []
        except Exception as e:
            self.logger.error(f"Error getting user activities: {str(e)}")
            return []
    
    def get_all_activities(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get all activities from Astra DB
        
        Args:
            limit: Maximum number of activities to return
            
        Returns:
            List[Dict]: List of activities
        """
        try:
            result = self.db.get_many(
                collection_name=self.activities_collection_name,
                limit=limit
            )
            
            return result if result else []
        except Exception as e:
            self.logger.error(f"Error getting all activities: {str(e)}")
            return []
    
    def get_similar_activities(
        self, 
        description: str, 
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Get activities similar to a description using vector search
        
        Args:
            description: Activity description to match
            limit: Maximum number of activities to return
            
        Returns:
            List[Dict]: List of similar activities
        """
        try:
            # Use vector search in Astra DB
            result = self.db.vector_find(
                collection_name=self.activities_collection_name,
                vector=description,  # Astra DB will generate embedding for this text
                limit=limit,
                include_similarity=True  # Include similarity scores
            )
            
            # Add similarity scores
            activities = []
            for activity in result:
                # Convert similarity score (0-1 range)
                if "similarity" in activity:
                    activity["similarity"] = activity["similarity"]
                else:
                    activity["similarity"] = 0.5  # Default if missing
                
                activities.append(activity)
            
            return activities
        except Exception as e:
            self.logger.error(f"Error getting similar activities: {str(e)}")
            # Fallback: return some random activities
            return self.get_all_activities(limit=limit)
    
    def get_activity(self, activity_id: str) -> Optional[Dict[str, Any]]:
        """
        Get an activity by ID
        
        Args:
            activity_id: Activity ID
            
        Returns:
            Dict or None: Activity data or None if not found
        """
        try:
            result = self.db.get_many(
                collection_name=self.activities_collection_name,
                filter={"_id": activity_id},
                limit=1
            )
            
            if result and len(result) > 0:
                return result[0]
            
            return None
        except Exception as e:
            self.logger.error(f"Error getting activity: {str(e)}")
            return None
    
    # Place operations
    def add_or_update_place(self, place_data: Dict[str, Any]) -> bool:
        """
        Add or update a place in Astra DB
        
        Args:
            place_data: Place data
            
        Returns:
            bool: Success status
        """
        try:
            place_id = place_data.get("id", str(uuid.uuid4()))
            
            # Ensure place has an ID
            place_data["_id"] = place_id
            
            # Add metadata if not present
            if "metadata" not in place_data:
                place_data["metadata"] = {}
            
            # Check if place exists
            existing_place = self.db.get_many(
                collection_name=self.places_collection_name,
                filter={"_id": place_id},
                limit=1
            )
            
            if existing_place and len(existing_place) > 0:
                # Update timestamp
                place_data["metadata"]["updated_at"] = datetime.now().isoformat()
                place_data["metadata"]["created_at"] = existing_place[0].get("metadata", {}).get(
                    "created_at", datetime.now().isoformat()
                )
                self.logger.info(f"Updated place {place_id}")
            else:
                # Set creation timestamp
                place_data["metadata"]["created_at"] = datetime.now().isoformat()
                place_data["metadata"]["updated_at"] = datetime.now().isoformat()
                self.logger.info(f"Added new place {place_id}")
            
            # Store place
            self.db.upsert(
                collection_name=self.places_collection_name,
                document=place_data
            )
            
            return True
        except Exception as e:
            self.logger.error(f"Error adding/updating place: {str(e)}")
            return False
    
    def get_place(self, place_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a place from Astra DB
        
        Args:
            place_id: Place ID
            
        Returns:
            Dict or None: Place data or None if not found
        """
        try:
            result = self.db.get_many(
                collection_name=self.places_collection_name,
                filter={"_id": place_id},
                limit=1
            )
            
            if result and len(result) > 0:
                return result[0]
            
            return None
        except Exception as e:
            self.logger.error(f"Error getting place: {str(e)}")
            return None
    
    def get_places_by_type(self, place_type: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get places by type
        
        Args:
            place_type: Type of place
            limit: Maximum number of places to return
            
        Returns:
            List[Dict]: List of places
        """
        try:
            # Query for places with the given type in their types array
            # This requires an array contains query which may vary by database
            # For simplicity, get all and filter
            result = self.db.get_many(
                collection_name=self.places_collection_name,
                limit=limit * 3  # Get more to allow for filtering
            )
            
            places = []
            if result:
                for place in result:
                    # Check if the type is in the types array
                    if "types" in place and place_type in place["types"]:
                        places.append(place)
                        if len(places) >= limit:
                            break
            
            return places
        except Exception as e:
            self.logger.error(f"Error getting places by type: {str(e)}")
            return []
    
    # Feedback operations
    def add_feedback(self, feedback_data: Dict[str, Any]) -> bool:
        """
        Add user feedback to Astra DB
        
        Args:
            feedback_data: Feedback data
            
        Returns:
            bool: Success status
        """
        try:
            feedback_id = str(uuid.uuid4())
            
            # Ensure feedback has a unique ID
            feedback_data["_id"] = feedback_id
            
            # Ensure feedback has a timestamp
            if "timestamp" not in feedback_data:
                feedback_data["timestamp"] = datetime.now().isoformat()
            
            # Add metadata if not present
            if "metadata" not in feedback_data:
                feedback_data["metadata"] = {}
            
            # Update metadata
            feedback_data["metadata"].update({
                "user_id": feedback_data.get("user_id", "unknown"),
                "activity_id": feedback_data.get("activity_id", "unknown"),
                "feedback_type": feedback_data.get("feedback_type", "unknown"),
                "timestamp": feedback_data.get("timestamp")
            })
            
            # Store feedback
            self.db.upsert(
                collection_name=self.feedback_collection_name,
                document=feedback_data
            )
            
            # Update user preferences based on feedback
            self.update_preferences_from_feedback(feedback_data)
            
            self.logger.info(f"Added feedback {feedback_id}")
            return True
        except Exception as e:
            self.logger.error(f"Error adding feedback: {str(e)}")
            return False
    
    def get_user_feedback(
        self, 
        user_id: str, 
        feedback_type: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get feedback for a user
        
        Args:
            user_id: User ID
            feedback_type: Optional filter by feedback type
            limit: Maximum number of feedbacks to return
            
        Returns:
            List[Dict]: List of feedback
        """
        try:
            # Build filter
            filter_query = {"metadata.user_id": user_id}
            if feedback_type:
                filter_query["metadata.feedback_type"] = feedback_type
            
            # Query feedback
            result = self.db.get_many(
                collection_name=self.feedback_collection_name,
                filter=filter_query,
                limit=limit
            )
            
            return result if result else []
        except Exception as e:
            self.logger.error(f"Error getting user feedback: {str(e)}")
            return []
    
    def get_recent_feedback(
        self, 
        user_id: str, 
        feedback_type: str,
        limit: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Get most recent feedback of a specific type for a user
        
        Args:
            user_id: User ID
            feedback_type: Feedback type
            limit: Maximum number of feedbacks to return
            
        Returns:
            List[Dict]: List of recent feedback
        """
        try:
            feedbacks = self.get_user_feedback(user_id, feedback_type)
            
            # Sort by timestamp (most recent first)
            sorted_feedbacks = sorted(
                feedbacks,
                key=lambda x: x.get("timestamp", ""),
                reverse=True
            )
            
            return sorted_feedbacks[:limit]
        except Exception as e:
            self.logger.error(f"Error getting recent feedback: {str(e)}")
            return []
    
    def get_all_feedback(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get all feedback from Astra DB
        
        Args:
            limit: Maximum number of feedbacks to return
            
        Returns:
            List[Dict]: List of feedback
        """
        try:
            result = self.db.get_many(
                collection_name=self.feedback_collection_name,
                limit=limit
            )
            
            return result if result else []
        except Exception as e:
            self.logger.error(f"Error getting all feedback: {str(e)}")
            return []
    
    def get_disliked_place_ids(self, user_id: str) -> List[str]:
        """
        Get IDs of places disliked by a user
        
        Args:
            user_id: User ID
            
        Returns:
            List[str]: List of disliked place IDs
        """
        try:
            # Get disliked outdoor activity feedback
            result = self.db.get_many(
                collection_name=self.feedback_collection_name,
                filter={
                    "metadata.user_id": user_id,
                    "metadata.feedback_type": "dislike"
                }
            )
            
            place_ids = []
            if result:
                for feedback in result:
                    # Only include outdoor activities with place_id
                    if feedback.get("activity_type") == "outdoor" and "activity_id" in feedback:
                        # Get the activity to find the place_id
                        activity = self.get_activity(feedback["activity_id"])
                        if activity and "place_id" in activity:
                            place_ids.append(activity["place_id"])
            
            return place_ids
        except Exception as e:
            self.logger.error(f"Error getting disliked place IDs: {str(e)}")
            return []
    
    # Statistics methods
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about the data in Astra DB
        
        Returns:
            Dict: Statistics
        """
        try:
            stats = {}
            
            # Count activities by type
            activities = self.get_all_activities()
            activity_types = [a.get("type") for a in activities if "type" in a]
            stats["activity_type_counts"] = dict(Counter(activity_types))
            
            # Count feedback by category
            feedback = self.get_all_feedback()
            categories = [f.get("interest_category") for f in feedback if "interest_category" in f]
            stats["category_counts"] = dict(Counter(categories))
            
            # Count feedback by type
            feedback_types = [f.get("feedback_type") for f in feedback if "feedback_type" in f]
            stats["feedback_type_counts"] = dict(Counter(feedback_types))
            
            # Count total users, activities, and places
            stats["user_count"] = len(self.get_all_users())
            stats["activity_count"] = len(activities)
            stats["feedback_count"] = len(feedback)
            
            return stats
        except Exception as e:
            self.logger.error(f"Error getting statistics: {str(e)}")
            return {}
