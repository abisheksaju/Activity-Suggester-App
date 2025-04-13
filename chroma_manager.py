import os
import uuid
import logging
import json
from typing import Dict, List, Any, Optional, Union
from datetime import datetime
from collections import Counter

import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions

class ChromaManager:
    """
    Manages interactions with ChromaDB for persistent storage of
    users, activities, preferences, and feedback.
    """
    
    def __init__(self, persist_directory: str = ".chromadb"):
        """Initialize ChromaDB client and collections"""
        self.logger = logging.getLogger('chroma_manager')
        
        # Create persist directory if it doesn't exist
        os.makedirs(persist_directory, exist_ok=True)
        
        # Initialize client
        self.client = chromadb.Client(Settings(
            persist_directory=persist_directory,
            chroma_db_impl="duckdb+parquet",
        ))
        
        # Set up embedding function
        self.embedding_func = embedding_functions.DefaultEmbeddingFunction()
        
        # Initialize collections
        self._init_collections()
    
    def _init_collections(self):
        """Initialize ChromaDB collections"""
        # Users collection - stores user profiles and preferences
        self.users_collection = self.client.get_or_create_collection(
            name="users",
            embedding_function=self.embedding_func,
            metadata={"description": "User profiles and preferences"}
        )
        
        # Activities collection - stores activity suggestions
        self.activities_collection = self.client.get_or_create_collection(
            name="activities",
            embedding_function=self.embedding_func,
            metadata={"description": "Activity suggestions"}
        )
        
        # Places collection - stores place metadata
        self.places_collection = self.client.get_or_create_collection(
            name="places",
            embedding_function=self.embedding_func,
            metadata={"description": "Place information"}
        )
        
        # Feedback collection - stores user feedback
        self.feedback_collection = self.client.get_or_create_collection(
            name="feedback",
            embedding_function=self.embedding_func,
            metadata={"description": "User feedback on activities"}
        )
        
        self.logger.info("ChromaDB collections initialized")
    
    # User operations
    def add_or_update_user(self, user_id: str, user_data: Dict[str, Any]) -> bool:
        """
        Add or update a user profile in ChromaDB
        
        Args:
            user_id: Unique ID for the user
            user_data: User profile data
            
        Returns:
            bool: Success status
        """
        try:
            # Convert user data to JSON string for storage
            user_json = json.dumps(user_data)
            
            # Check if user exists
            existing_users = self.users_collection.get(
                ids=[user_id],
                include=["metadatas"]
            )
            
            if existing_users["ids"]:
                # Update existing user
                self.users_collection.update(
                    ids=[user_id],
                    documents=[user_json],
                    metadatas=[{"updated_at": datetime.now().isoformat()}]
                )
                self.logger.info(f"Updated user {user_id}")
            else:
                # Add new user
                self.users_collection.add(
                    ids=[user_id],
                    documents=[user_json],
                    metadatas=[{
                        "created_at": datetime.now().isoformat(),
                        "updated_at": datetime.now().isoformat()
                    }]
                )
                self.logger.info(f"Added new user {user_id}")
                
                # Initialize preferences
                self._initialize_user_preferences(user_id, user_data)
            
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
                "user_id": user_id,
                "category_preferences": initial_interests,
                "liked_places": [],
                "disliked_places": []
            }
            
            # Store preferences as a separate entry for easier updates
            preferences_id = f"{user_id}_preferences"
            
            self.users_collection.add(
                ids=[preferences_id],
                documents=[json.dumps(preferences)],
                metadatas=[{
                    "type": "preferences",
                    "user_id": user_id,
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat()
                }]
            )
            
            self.logger.info(f"Initialized preferences for user {user_id}")
        except Exception as e:
            self.logger.error(f"Error initializing user preferences: {str(e)}")
    
    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a user profile from ChromaDB
        
        Args:
            user_id: Unique ID for the user
            
        Returns:
            Dict or None: User profile data or None if not found
        """
        try:
            result = self.users_collection.get(
                ids=[user_id],
                include=["documents"]
            )
            
            if result["ids"] and result["documents"]:
                # Parse JSON string back to dictionary
                return json.loads(result["documents"][0])
            
            return None
        except Exception as e:
            self.logger.error(f"Error getting user: {str(e)}")
            return None
    
    def delete_user(self, user_id: str) -> bool:
        """
        Delete a user profile from ChromaDB
        
        Args:
            user_id: Unique ID for the user
            
        Returns:
            bool: Success status
        """
        try:
            # Delete user profile
            self.users_collection.delete(ids=[user_id])
            
            # Delete user preferences
            preferences_id = f"{user_id}_preferences"
            self.users_collection.delete(ids=[preferences_id])
            
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
            # Query feedback by user_id in metadata
            result = self.feedback_collection.get(
                where={"user_id": user_id},
                include=["ids"]
            )
            
            if result["ids"]:
                self.feedback_collection.delete(ids=result["ids"])
                self.logger.info(f"Deleted {len(result['ids'])} feedback entries for user {user_id}")
        except Exception as e:
            self.logger.error(f"Error deleting user feedback: {str(e)}")
    
    def _delete_user_activities(self, user_id: str):
        """Delete all activities for a user"""
        try:
            # Query activities by user_id in metadata
            result = self.activities_collection.get(
                where={"user_id": user_id},
                include=["ids"]
            )
            
            if result["ids"]:
                self.activities_collection.delete(ids=result["ids"])
                self.logger.info(f"Deleted {len(result['ids'])} activities for user {user_id}")
        except Exception as e:
            self.logger.error(f"Error deleting user activities: {str(e)}")
    
    def get_all_users(self) -> List[Dict[str, Any]]:
        """
        Get all user profiles from ChromaDB
        
        Returns:
            List[Dict]: List of user profiles
        """
        try:
            # Get all users (excluding preferences entries)
            result = self.users_collection.get(
                where={"$not": {"type": "preferences"}},
                include=["documents", "metadatas"]
            )
            
            users = []
            if result["ids"]:
                for i, doc in enumerate(result["documents"]):
                    user = json.loads(doc)
                    # Add metadata
                    if "metadatas" in result and result["metadatas"]:
                        user["metadata"] = result["metadatas"][i]
                    users.append(user)
            
            return users
        except Exception as e:
            self.logger.error(f"Error getting all users: {str(e)}")
            return []
    
    # User preferences operations
    def get_user_preferences(self, user_id: str) -> Dict[str, Any]:
        """
        Get user preferences from ChromaDB
        
        Args:
            user_id: Unique ID for the user
            
        Returns:
            Dict: User preferences
        """
        try:
            preferences_id = f"{user_id}_preferences"
            result = self.users_collection.get(
                ids=[preferences_id],
                include=["documents"]
            )
            
            if result["ids"] and result["documents"]:
                # Parse JSON string back to dictionary
                return json.loads(result["documents"][0])
            
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
            
            if category and category in preferences["category_preferences"]:
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
            if len(preferences["liked_places"]) > 20:
                preferences["liked_places"] = preferences["liked_places"][-20:]
            if len(preferences["disliked_places"]) > 20:
                preferences["disliked_places"] = preferences["disliked_places"][-20:]
            
            # Update preferences in ChromaDB
            preferences_id = f"{user_id}_preferences"
            self.users_collection.update(
                ids=[preferences_id],
                documents=[json.dumps(preferences)],
                metadatas=[{
                    "type": "preferences",
                    "user_id": user_id,
                    "updated_at": datetime.now().isoformat()
                }]
            )
            
            self.logger.info(f"Updated preferences for user {user_id}")
        except Exception as e:
            self.logger.error(f"Error updating preferences from feedback: {str(e)}")
    
    # Activity operations
    def add_activity(self, activity_data: Dict[str, Any]) -> bool:
        """
        Add a new activity to ChromaDB
        
        Args:
            activity_data: Activity data
            
        Returns:
            bool: Success status
        """
        try:
            activity_id = activity_data.get("id", str(uuid.uuid4()))
            user_id = activity_data.get("user_id", "unknown")
            activity_type = activity_data.get("type", "unknown")
            
            # Convert to JSON string
            activity_json = json.dumps(activity_data)
            
            # Build metadata
            metadata = {
                "user_id": user_id,
                "type": activity_type,
                "timestamp": datetime.now().isoformat()
            }
            
            # Add activity to collection
            self.activities_collection.add(
                ids=[activity_id],
                documents=[activity_json],
                metadatas=[metadata]
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
            result = self.activities_collection.get(
                ids=[activity_id],
                include=["documents"]
            )
            
            if result["ids"] and result["documents"]:
                # Parse JSON string back to dictionary
                activity_data = json.loads(result["documents"][0])
                
                # Update image URL
                activity_data["image_url"] = image_url
                
                # Convert back to JSON string
                activity_json = json.dumps(activity_data)
                
                # Update in ChromaDB
                self.activities_collection.update(
                    ids=[activity_id],
                    documents=[activity_json]
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
            # Build query
            where_clause = {"user_id": user_id}
            if activity_type:
                where_clause["type"] = activity_type
            
            # Query activities
            result = self.activities_collection.get(
                where=where_clause,
                include=["documents", "metadatas"],
                limit=limit
            )
            
            activities = []
            if result["ids"]:
                for i, doc in enumerate(result["documents"]):
                    activity = json.loads(doc)
                    # Add metadata
                    if "metadatas" in result and result["metadatas"]:
                        activity["metadata"] = result["metadatas"][i]
                    activities.append(activity)
            
            return activities
        except Exception as e:
            self.logger.error(f"Error getting user activities: {str(e)}")
            return []
    
    def get_all_activities(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get all activities from ChromaDB
        
        Args:
            limit: Maximum number of activities to return
            
        Returns:
            List[Dict]: List of activities
        """
        try:
            result = self.activities_collection.get(
                include=["documents", "metadatas"],
                limit=limit
            )
            
            activities = []
            if result["ids"]:
                for i, doc in enumerate(result["documents"]):
                    activity = json.loads(doc)
                    # Add metadata
                    if "metadatas" in result and result["metadatas"]:
                        activity["metadata"] = result["metadatas"][i]
                    activities.append(activity)
            
            return activities
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
            result = self.activities_collection.query(
                query_texts=[description],
                n_results=limit,
                include=["documents", "metadatas", "distances"]
            )
            
            activities = []
            if result["ids"] and result["ids"][0]:
                for i, doc in enumerate(result["documents"][0]):
                    activity = json.loads(doc)
                    # Add metadata and similarity score
                    if "metadatas" in result and result["metadatas"][0]:
                        activity["metadata"] = result["metadatas"][0][i]
                    if "distances" in result and result["distances"][0]:
                        activity["similarity"] = 1.0 - min(result["distances"][0][i], 1.0)
                    activities.append(activity)
            
            return activities
        except Exception as e:
            self.logger.error(f"Error getting similar activities: {str(e)}")
            return []
    
    # Place operations
    def add_or_update_place(self, place_data: Dict[str, Any]) -> bool:
        """
        Add or update a place in ChromaDB
        
        Args:
            place_data: Place data
            
        Returns:
            bool: Success status
        """
        try:
            place_id = place_data.get("id", str(uuid.uuid4()))
            
            # Convert to JSON string
            place_json = json.dumps(place_data)
            
            # Check if place exists
            existing_places = self.places_collection.get(
                ids=[place_id],
                include=["metadatas"]
            )
            
            if existing_places["ids"]:
                # Update existing place
                self.places_collection.update(
                    ids=[place_id],
                    documents=[place_json],
                    metadatas=[{"updated_at": datetime.now().isoformat()}]
                )
                self.logger.info(f"Updated place {place_id}")
            else:
                # Add new place
                self.places_collection.add(
                    ids=[place_id],
                    documents=[place_json],
                    metadatas=[{
                        "created_at": datetime.now().isoformat(),
                        "updated_at": datetime.now().isoformat()
                    }]
                )
                self.logger.info(f"Added new place {place_id}")
            
            return True
        except Exception as e:
            self.logger.error(f"Error adding/updating place: {str(e)}")
            return False
    
    def get_place(self, place_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a place from ChromaDB
        
        Args:
            place_id: Place ID
            
        Returns:
            Dict or None: Place data or None if not found
        """
        try:
            result = self.places_collection.get(
                ids=[place_id],
                include=["documents"]
            )
            
            if result["ids"] and result["documents"]:
                # Parse JSON string back to dictionary
                return json.loads(result["documents"][0])
            
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
            # Use the 'where' parameter to filter by type (contained in 'types' array)
            # Since ChromaDB doesn't support array contains, we'll get all and filter
            result = self.places_collection.get(
                include=["documents"],
                limit=limit * 10  # Get more to allow for filtering
            )
            
            places = []
            if result["ids"] and result["documents"]:
                for doc in result["documents"]:
                    place = json.loads(doc)
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
        Add user feedback to ChromaDB
        
        Args:
            feedback_data: Feedback data
            
        Returns:
            bool: Success status
        """
        try:
            feedback_id = str(uuid.uuid4())
            
            # Ensure feedback has a timestamp
            if "timestamp" not in feedback_data:
                feedback_data["timestamp"] = datetime.now().isoformat()
            
            # Convert to JSON string
            feedback_json = json.dumps(feedback_data)
            
            # Extract metadata
            metadata = {
                "user_id": feedback_data.get("user_id", "unknown"),
                "activity_id": feedback_data.get("activity_id", "unknown"),
                "feedback_type": feedback_data.get("feedback_type", "unknown"),
                "timestamp": feedback_data.get("timestamp")
            }
            
            # Add feedback to collection
            self.feedback_collection.add(
                ids=[feedback_id],
                documents=[feedback_json],
                metadatas=[metadata]
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
            # Build query
            where_clause = {"user_id": user_id}
            if feedback_type:
                where_clause["feedback_type"] = feedback_type
            
            # Query feedback
            result = self.feedback_collection.get(
                where=where_clause,
                include=["documents", "metadatas"],
                limit=limit
            )
            
            feedbacks = []
            if result["ids"]:
                for i, doc in enumerate(result["documents"]):
                    feedback = json.loads(doc)
                    # Add metadata
                    if "metadatas" in result and result["metadatas"]:
                        feedback["metadata"] = result["metadatas"][i]
                    feedbacks.append(feedback)
            
            return feedbacks
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
        Get all feedback from ChromaDB
        
        Args:
            limit: Maximum number of feedbacks to return
            
        Returns:
            List[Dict]: List of feedback
        """
        try:
            result = self.feedback_collection.get(
                include=["documents", "metadatas"],
                limit=limit
            )
            
            feedbacks = []
            if result["ids"]:
                for i, doc in enumerate(result["documents"]):
                    feedback = json.loads(doc)
                    # Add metadata
                    if "metadatas" in result and result["metadatas"]:
                        feedback["metadata"] = result["metadatas"][i]
                    feedbacks.append(feedback)
            
            return feedbacks
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
            result = self.feedback_collection.get(
                where={
                    "user_id": user_id,
                    "feedback_type": "dislike"
                },
                include=["documents"]
            )
            
            place_ids = []
            if result["ids"]:
                for doc in result["documents"]:
                    feedback = json.loads(doc)
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
    
    def get_activity(self, activity_id: str) -> Optional[Dict[str, Any]]:
        """
        Get an activity by ID
        
        Args:
            activity_id: Activity ID
            
        Returns:
            Dict or None: Activity data or None if not found
        """
        try:
            result = self.activities_collection.get(
                ids=[activity_id],
                include=["documents"]
            )
            
            if result["ids"] and result["documents"]:
                # Parse JSON string back to dictionary
                return json.loads(result["documents"][0])
            
            return None
        except Exception as e:
            self.logger.error(f"Error getting activity: {str(e)}")
            return None
    
    # Statistics methods
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about the data in ChromaDB
        
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
