import logging
import uuid
from typing import Dict, Any, List, Callable, Optional, TypedDict
from datetime import datetime

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
import google.generativeai as genai

class ActivityState(TypedDict):
    """Type definition for the state object passed between graph nodes"""
    user: Dict
    user_id: str
    interests: Dict[str, float]
    top_interest: Optional[str]
    activity_type: Optional[str]
    recommendation: Optional[Dict]
    feedback: Optional[Dict]
    detailed_description: Optional[str]
    maps_html: Optional[str]
    user_feedback: Optional[str]
    errors: List[str]

class ActivitySuggesterGraph:
    """LangGraph implementation of activity suggestion flow"""
    
    def __init__(self, model, chroma_manager, api_keys):
        """Initialize the ActivitySuggesterGraph with dependencies"""
        self.model = model
        self.chroma_manager = chroma_manager
        self.api_keys = api_keys
        self.logger = logging.getLogger('activity_graph')
        
        # Build the graph
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """
        Build the LangGraph for activity suggestions
        
        Graph structure:
        UserContextNode -> InterestAnalysisNode -> ActivityTypeDecisionNode -> 
        [IndoorSuggestionNode or OutdoorSuggestionNode] -> ImageFetchingNode -> END
        """
        # Create the state graph
        graph = StateGraph(ActivityState)
        
        # Add nodes
        graph.add_node("user_context", self._user_context_node)
        graph.add_node("interest_analysis", self._interest_analysis_node)
        graph.add_node("activity_type_decision", self._activity_type_decision_node)
        graph.add_node("indoor_suggestion", self._indoor_suggestion_node)
        graph.add_node("outdoor_suggestion", self._outdoor_suggestion_node)
        graph.add_node("image_fetching", self._image_fetching_node)
        
        # Add edges
        graph.add_edge("user_context", "interest_analysis")
        graph.add_edge("interest_analysis", "activity_type_decision")
        
        # Conditional routing after activity type decision
        graph.add_conditional_edges(
            "activity_type_decision",
            self._route_by_activity_type,
            {
                "indoor": "indoor_suggestion",
                "outdoor": "outdoor_suggestion"
            }
        )
        
        # Both suggestion nodes route to image fetching
        graph.add_edge("indoor_suggestion", "image_fetching")
        graph.add_edge("outdoor_suggestion", "image_fetching")
        
        # Image fetching routes to the end
        graph.add_edge("image_fetching", END)
        
        # Set the entry point
        graph.set_entry_point("user_context")
        
        return graph
    
    # Node implementations
    def _user_context_node(self, state: ActivityState) -> ActivityState:
        """Process and enhance user context"""
        try:
            user = state.get("user", {})
            
            # Make sure we have a user ID
            if "user_id" not in user:
                user["user_id"] = str(uuid.uuid4())
            
            # Get or create user from ChromaDB
            user_from_db = self.chroma_manager.get_user(user["user_id"])
            if not user_from_db:
                # New user, store in ChromaDB
                self.chroma_manager.add_or_update_user(user["user_id"], user)
            else:
                # Merge with existing user data - prefer existing preferences
                if "interests" in user_from_db:
                    user["interests"] = user_from_db["interests"]
            
            # Update state
            state["user"] = user
            state["user_id"] = user["user_id"]
            
            return state
        except Exception as e:
            self.logger.error(f"Error in user_context_node: {str(e)}")
            state["errors"] = state.get("errors", []) + [f"Error processing user context: {str(e)}"]
            return state
    
    def _interest_analysis_node(self, state: ActivityState) -> ActivityState:
        """Analyze user interests and determine top interest"""
        try:
            user = state.get("user", {})
            user_id = state.get("user_id")
            
            # Get adjusted interests based on feedback from ChromaDB
            adjusted_interests = self.chroma_manager.get_user_preferences(user_id)["category_preferences"]
            
            if not adjusted_interests and "interests" in user:
                # Use original interests if no adjusted interests
                adjusted_interests = user["interests"]
            
            # Call LLM to rank interests
            prompt = f"""
            You are a smart assistant that ranks user interests in the context of the moment.

            User Context:
            - City: {user['location']['city']}
            - Weather: {user['weather']}
            - Current Time: {user['current_time']}
            - Free Hours: {user['free_hours']}
            - Interests (with scores): {adjusted_interests}

            Based on this context, rank the categories from most to least relevant **for recommending an activity right now**.

            Return a ranked list like this:
            1. travel
            2. gaming
            3. shopping
            ...

            Only return the list — no explanations.
            """
            
            # Call Gemini model
            response = self.model.generate_content(prompt)
            ranked_categories = response.text.strip().split('\n')
            
            # Extract top interest
            top_interest = ranked_categories[0].split(".")[1].strip()
            
            # Update state
            state["interests"] = adjusted_interests
            state["top_interest"] = top_interest
            
            return state
        except Exception as e:
            self.logger.error(f"Error in interest_analysis_node: {str(e)}")
            state["errors"] = state.get("errors", []) + [f"Error analyzing interests: {str(e)}"]
            state["top_interest"] = "food"  # Default fallback
            return state
    
    def _activity_type_decision_node(self, state: ActivityState) -> ActivityState:
        """Decide between indoor and outdoor activity"""
        try:
            user = state.get("user", {})
            top_interest = state.get("top_interest")
            
            # Build prompt
            prompt = f"""
            Based on this context, decide if I should suggest an indoor or outdoor activity.
            Just respond with "indoor" or "outdoor".
            
            User context:
            - Current weather: {user.get("weather", "Unknown")}
            - Current time: {user.get("current_time", "Unknown")}
            - Their top interest: {top_interest}
            - Free hours: {user.get("free_hours", "Unknown")}
            - Location: {user['location']['city']}
            
            Consider:
            - If it's late evening, raining, or very hot, indoor might be better
            - If it's morning or daytime with good weather, outdoor might be better
            - Also consider the interest - some activities like gaming are typically indoor
            - Also consider the location of the user
            """
            
            # Call Gemini model
            response = self.model.generate_content(prompt)
            decision = response.text.strip().lower()
            
            # Validate decision
            if decision not in ["indoor", "outdoor"]:
                self.logger.warning(f"Invalid activity type decision: {decision}, defaulting to indoor")
                decision = "indoor"
            
            # Update state
            state["activity_type"] = decision
            
            return state
        except Exception as e:
            self.logger.error(f"Error in activity_type_decision_node: {str(e)}")
            state["errors"] = state.get("errors", []) + [f"Error deciding activity type: {str(e)}"]
            state["activity_type"] = "indoor"  # Default to indoor on error
            return state
    
    def _indoor_suggestion_node(self, state: ActivityState) -> ActivityState:
        """Generate indoor activity suggestion"""
        try:
            user = state.get("user", {})
            top_interest = state.get("top_interest")
            user_feedback = state.get("user_feedback")
            user_id = state.get("user_id")
            
            # Get previous activities for this user to avoid repetition
            previous_activities = self.chroma_manager.get_user_activities(
                user_id, 
                activity_type="indoor", 
                limit=5
            )
            
            # Add previous activities to the prompt to avoid repetition
            previous_note = ""
            if previous_activities:
                previous_note = "\nPreviously suggested indoor activities (DO NOT suggest these again):\n"
                previous_note += "\n".join([f"- {item['description']}" for item in previous_activities])
                previous_note += "\n\nPlease suggest something DIFFERENT from these previous recommendations."
            
            # Include user feedback if available
            feedback_note = "" if not user_feedback else f"{user_feedback} "
            
            # Build the prompt
            prompt = f"""
            {feedback_note}Suggest a specific indoor activity related to {top_interest} that I can do at home or nearby.
            
            My context:
            - Current time: {user.get("current_time", "Unknown")}
            - I have {user.get("free_hours", "Unknown")} free hours
            - My top interest right now: {top_interest}
            - My city right now: {user['location']['city']}
            {previous_note}

            ❗ Choose only one activity. Do not list or compare options. 
            Make your response in 1-2 short, fun, personal sentences that help me decide what to do right now.
            Be specific and practical. Recommend something realistic, not generic. Your output would be displayed on the lockscreen of the users phone
            """
            
            # Call Gemini model
            response = self.model.generate_content(prompt)
            activity_description = response.text.strip()
            
            # Generate a unique ID for this activity
            activity_id = str(uuid.uuid4())
            
            # Store activity in ChromaDB
            activity_data = {
                "id": activity_id,
                "type": "indoor",
                "name": f"Indoor {top_interest} Activity",
                "description": activity_description,
                "activity_type": top_interest,
                "timestamp": datetime.now().isoformat(),
                "user_id": user_id
            }
            
            self.chroma_manager.add_activity(activity_data)
            
            # Create recommendation object
            recommendation = {
                "id": activity_id,
                "type": "indoor",
                "name": f"Indoor {top_interest} Activity",
                "description": activity_description,
                "activity_type": top_interest,
                "image_url": None  # Will be filled by image_fetching_node
            }
            
            # Update state
            state["recommendation"] = recommendation
            
            return state
        except Exception as e:
            self.logger.error(f"Error in indoor_suggestion_node: {str(e)}")
            state["errors"] = state.get("errors", []) + [f"Error generating indoor suggestion: {str(e)}"]
            
            # Fallback recommendation
            state["recommendation"] = {
                "id": str(uuid.uuid4()),
                "type": "indoor",
                "name": "Indoor Activity",
                "description": "Try a fun indoor activity related to your interests!",
                "activity_type": state.get("top_interest", "activity"),
                "image_url": None
            }
            
            return state
    
    def _outdoor_suggestion_node(self, state: ActivityState) -> ActivityState:
        """Generate outdoor activity suggestion by finding and ranking places"""
        try:
            user = state.get("user", {})
            top_interest = state.get("top_interest")
            user_feedback = state.get("user_feedback")
            user_id = state.get("user_id")
            
            # Import here to avoid circular imports
            from place_utils import fetch_places, choose_place
            
            # Fetch places from Google Maps
            places = fetch_places(user, top_interest, self.api_keys["google_maps"])
            
            # Get previously disliked places for this user
            disliked_place_ids = self.chroma_manager.get_disliked_place_ids(user_id)
            
            # Filter out disliked places
            filtered_places = [
                place for place in places 
                if place.get("place_id") not in disliked_place_ids
            ]
            
            # If we've filtered out all places, fall back to the original list
            if not filtered_places and places:
                filtered_places = places
            
            # Choose one place - pass user feedback to the LLM
            selected_place, description = choose_place(
                user, 
                filtered_places, 
                self.model, 
                user_feedback,
                self.api_keys["ors"],
                self.chroma_manager.get_user_preferences(user_id)
            )
            
            if selected_place:
                # Generate a unique ID for this activity
                activity_id = str(uuid.uuid4())
                
                # Get image URL if available
                from image_utils import fetch_place_image
                image_url = fetch_place_image(selected_place, self.api_keys["google_maps"])
                
                # Create place data
                place_data = {
                    "id": selected_place.get("place_id", activity_id),
                    "name": selected_place.get("name", "Unknown place"),
                    "address": selected_place.get("vicinity", "Unknown location"),
                    "location": {
                        "lat": selected_place.get("geometry", {}).get("location", {}).get("lat"),
                        "lng": selected_place.get("geometry", {}).get("location", {}).get("lng")
                    },
                    "types": selected_place.get("types", []),
                    "rating": selected_place.get("rating"),
                    "user_ratings_total": selected_place.get("user_ratings_total")
                }
                
                # Store place in ChromaDB
                self.chroma_manager.add_or_update_place(place_data)
                
                # Store activity in ChromaDB
                activity_data = {
                    "id": activity_id,
                    "type": "outdoor",
                    "name": selected_place.get("name", "Unknown place"),
                    "description": description,
                    "place_id": selected_place.get("place_id"),
                    "activity_type": top_interest,
                    "timestamp": datetime.now().isoformat(),
                    "user_id": user_id
                }
                
                self.chroma_manager.add_activity(activity_data)
                
                # Create recommendation object
                recommendation = {
                    "id": activity_id,
                    "type": "outdoor",
                    "place": selected_place,
                    "name": selected_place.get("name", "Unknown place"),
                    "description": description,
                    "activity_type": top_interest,
                    "image_url": image_url
                }
                
                # Update state
                state["recommendation"] = recommendation
                
                return state
            else:
                # Fall back to indoor suggestion
                self.logger.warning("No outdoor places found, falling back to indoor")
                return self._indoor_suggestion_node(state)
                
        except Exception as e:
            self.logger.error(f"Error in outdoor_suggestion_node: {str(e)}")
            state["errors"] = state.get("errors", []) + [f"Error generating outdoor suggestion: {str(e)}"]
            
            # Fall back to indoor suggestion
            return self._indoor_suggestion_node(state)
    
    def _image_fetching_node(self, state: ActivityState) -> ActivityState:
        """Fetch relevant image for the activity"""
        try:
            recommendation = state.get("recommendation", {})
            
            # Skip if recommendation already has an image
            if recommendation.get("image_url"):
                return state
            
            # Import image utilities
            from image_utils import (
                extract_keywords_from_prompt, 
                extract_main_keywords,
                fetch_image_for_keyword
            )
            
            if recommendation.get("type") == "indoor":
                # For indoor activities, extract keywords and fetch related image
                activity_description = recommendation.get("description", "")
                activity_type = recommendation.get("activity_type", "activity")
                
                # Try to extract keywords
                try:
                    keywords = extract_keywords_from_prompt(activity_description)
                    
                    # Try each keyword until we find an image
                    for keyword in keywords:
                        if not keyword or len(keyword.strip()) < 3:
                            continue
                        
                        self.logger.info(f"Trying to fetch image for keyword: {keyword}")
                        img_url = fetch_image_for_keyword(
                            keyword, 
                            self.api_keys["google_maps"]
                        )
                        
                        if img_url:
                            recommendation["image_url"] = img_url
                            recommendation["keyword"] = keyword
                            self.logger.info(f"Found image for keyword: {keyword}")
                            break
                except Exception as kw_err:
                    self.logger.error(f"Error extracting keywords: {str(kw_err)}")
                
                # If still no image, try with the backup method
                if not recommendation.get("image_url"):
                    main_keyword = extract_main_keywords(activity_description)
                    if main_keyword and len(main_keyword) >= 3:
                        self.logger.info(f"Trying fallback keyword: {main_keyword}")
                        image_url = fetch_image_for_keyword(
                            main_keyword, 
                            self.api_keys["google_maps"]
                        )
                        
                        if image_url:
                            recommendation["image_url"] = image_url
                            recommendation["keyword"] = main_keyword
                
                # Last resort - try with the activity type
                if not recommendation.get("image_url"):
                    self.logger.info(f"Using activity type as keyword: {activity_type}")
                    from image_utils import fetch_unsplash_image
                    image_url = fetch_unsplash_image(activity_type)
                    
                    if image_url:
                        recommendation["image_url"] = image_url
                        recommendation["keyword"] = activity_type
            
            # Update the recommendation in state
            state["recommendation"] = recommendation
            
            # If we have an updated image URL, update the activity in ChromaDB
            if recommendation.get("image_url") and recommendation.get("id"):
                self.chroma_manager.update_activity_image(
                    recommendation["id"], 
                    recommendation["image_url"]
                )
            
            return state
        except Exception as e:
            self.logger.error(f"Error in image_fetching_node: {str(e)}")
            state["errors"] = state.get("errors", []) + [f"Error fetching image: {str(e)}"]
            return state
    
    # Helper functions for conditional routing
    def _route_by_activity_type(self, state: ActivityState) -> str:
        """Route to indoor or outdoor suggestion node based on activity type"""
        activity_type = state.get("activity_type", "indoor")
        return activity_type
    
    # Public methods
    def run(self, initial_state: Dict[str, Any]) -> Dict[str, Any]:
        """Run the activity suggestion graph"""
        # Convert dict to ActivityState
        state = ActivityState(
            user=initial_state.get("user", {}),
            user_id=initial_state.get("user", {}).get("user_id", ""),
            interests={},
            top_interest=None,
            activity_type=None,
            recommendation=None,
            feedback=None,
            detailed_description=None,
            maps_html=None,
            user_feedback=initial_state.get("user_feedback"),
            errors=initial_state.get("errors", [])
        )
        
        # Run the graph
        result = self.graph.invoke(state)
        
        # Convert back to dict
        return dict(result)
    
    def expand_details(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Expand the details of a recommendation"""
        try:
            user = state.get("user", {})
            recommendation = state.get("recommendation", {})
            
            prompt = f"""
            Please provide more detailed information about this activity suggestion:
            "{recommendation.get('description', 'Unknown activity')}"
            
            The user's main interest is: {recommendation.get('activity_type', 'Unknown')}
            Current time: {user.get("current_time", "Unknown")}
            Free hours: {user.get("free_hours", "Unknown")}
            
            Provide 5-6 sentences with:
            1. More details about this specific activity
            2. Why it's a good fit for the user now
            3. Specific things to look for or enjoy
            
            Be specific, practical and personal. Make it sound exciting but realistic.
            """
            
            # Call Gemini model
            response = self.model.generate_content(prompt)
            detailed_description = response.text.strip()
            
            # Add maps link for outdoor activities
            maps_html = ""
            if recommendation.get("type") == "outdoor" and recommendation.get("place"):
                place = recommendation.get("place")
                if place.get("place_id"):
                    place_id = place.get("place_id")
                    place_name = place.get("name", "Location")
                    maps_link = f"https://www.google.com/maps/place/?q=place_id:{place_id}"
                    
                    # Create a button to open Google Maps
                    maps_html = f"""
                    <div style="margin-top: 20px; margin-bottom: 20px;">
                        <h4>📍 Map Location</h4>
                        <a href="{maps_link}" target="_blank">
                            <button style="background-color: #4285F4; color: white; padding: 10px 15px; 
                            border: none; border-radius: 5px; cursor: pointer;">
                                Open {place_name} in Google Maps
                            </button>
                        </a>
                    </div>
                    """
            
            # Update the result
            result = dict(state)
            result["detailed_description"] = detailed_description
            result["maps_html"] = maps_html
            
            return result
        except Exception as e:
            self.logger.error(f"Error in expand_details: {str(e)}")
            result = dict(state)
            result["detailed_description"] = "I'm sorry, I couldn't generate additional details right now."
            result["maps_html"] = ""
            result["errors"] = result.get("errors", []) + [f"Error expanding details: {str(e)}"]
            return result
