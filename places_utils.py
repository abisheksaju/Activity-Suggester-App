import random
import logging
from typing import Tuple, List, Dict, Any, Optional

import googlemaps
import openrouteservice

from api_utils import safe_api_call, APIError, LLMError

# Set up logging
logger = logging.getLogger('place_utils')

@safe_api_call
def fetch_places(user: Dict[str, Any], interest_type: str, api_key: str) -> List[Dict[str, Any]]:
    """
    Fetch places from Google Maps Places API based on user context and interest
    
    Args:
        user: User context data
        interest_type: Interest type to search for
        api_key: Google Maps API key
        
    Returns:
        List[Dict]: List of places
    """
    gmaps = googlemaps.Client(key=api_key)
    
    # Get location from user
    lat = user.get('location', {}).get('lat')
    lon = user.get('location', {}).get('lon')
    
    if not lat or not lon:
        logger.warning("Missing user location coordinates")
        return []
    
    # Map interest types to Google Maps place types
    place_type_mapping = {
        'food': 'restaurant',
        'shopping': 'shopping_mall',
        'travel': 'tourist_attraction',
        'news': 'library',
        'gaming': 'amusement_park',
        'cooking': 'store'
    }
    
    # Get place type from interest
    place_type = place_type_mapping.get(interest_type, 'point_of_interest')
    
    # Search for places
    places_result = gmaps.places_nearby(
        location=(lat, lon),
        radius=20000,  # 20km radius
        type=place_type,
        open_now=True
    )
    
    return places_result.get('results', [])

def build_personalized_context(user: Dict[str, Any], top_interest: str, user_preferences: Dict[str, Any]) -> str:
    """
    Build personalized context string based on user preferences
    
    Args:
        user: User context data
        top_interest: Top interest
        user_preferences: User preferences from ChromaDB
        
    Returns:
        str: Personalized context string
    """
    context = []
    
    # Add information about category preferences
    if user_preferences.get("category_preferences"):
        top_categories = sorted(
            user_preferences["category_preferences"].items(), 
            key=lambda x: x[1], 
            reverse=True
        )[:3]
        
        categories_text = ", ".join([f"{cat} ({score:.1f})" for cat, score in top_categories])
        context.append(f"Top categories: {categories_text}")
    
    # Add information about liked places
    if user_preferences.get("liked_places"):
        recent_likes = [item['name'] for item in user_preferences["liked_places"][-3:]]
        context.append(f"Recently liked: {', '.join(recent_likes)}")
    
    # Add information about disliked places
    if user_preferences.get("disliked_places"):
        recent_dislikes = [item['name'] for item in user_preferences["disliked_places"][-3:]]
        context.append(f"Recently disliked: {', '.join(recent_dislikes)}")
    
    # Return the combined context
    if context:
        return "\n- " + "\n- ".join(context)
    return "No preference history available."

@safe_api_call
def get_route_duration(origin: Tuple[float, float], destination: Tuple[float, float], ors_client) -> Optional[int]:
    """
    Get the route duration between two points using OpenRouteService
    
    Args:
        origin: Origin coordinates (lon, lat)
        destination: Destination coordinates (lon, lat)
        ors_client: OpenRouteService client
        
    Returns:
        int or None: Duration in minutes or None if not found
    """
    # Make sure coordinates are valid
    if not all(origin) or not all(destination):
        return None
    
    # Request route from ORS API
    route = ors_client.directions(
        coordinates=[origin, destination],
        profile='driving-car',
        format='geojson'
    )
    
    # Extract duration in seconds and convert to minutes
    if route and 'features' in route and len(route['features']) > 0:
        duration_seconds = route['features'][0]['properties']['summary']['duration']
        return round(duration_seconds / 60)  # Convert to minutes
    
    return None

@safe_api_call
def choose_place(
    user: Dict[str, Any], 
    places: List[Dict[str, Any]], 
    model, 
    user_feedback: Optional[str],
    ors_api_key: str,
    user_preferences: Dict[str, Any]
) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Choose the best place from options and return selected_place and LLM description
    
    Args:
        user: User context data
        places: List of places from Google Maps API
        model: LLM model instance
        user_feedback: Optional user feedback
        ors_api_key: OpenRouteService API key
        user_preferences: User preferences from ChromaDB
        
    Returns:
        Tuple[Dict or None, str]: Selected place and description
    """
    if not places:
        logger.warning("No places found to choose from")
        return None, "We couldn't find any interesting places nearby. Let's suggest an indoor activity instead."

    try:
        # Initialize ORS client
        ors_client = openrouteservice.Client(key=ors_api_key)
        
        # Prepare enriched places with travel time
        enriched_places = []

        lat = user.get("location", {}).get("lat")
        lon = user.get("location", {}).get("lon")
        top_interest = user.get("top_interest", "activity")

        if not lat or not lon:
            return None, "We couldn't get enough data to find outdoor suggestions."

        personalized_context = build_personalized_context(user, top_interest, user_preferences)

        for idx, place in enumerate(places[:5]):
            try:
                place_lat = place["geometry"]["location"]["lat"]
                place_lon = place["geometry"]["location"]["lng"]
                travel_time_mins = get_route_duration((lon, lat), (place_lon, place_lat), ors_client)
                travel_time_mins = travel_time_mins * 2 if travel_time_mins else "unknown"

                enriched_places.append({
                    "prominence_rank": idx + 1,
                    "place": place,
                    "name": place.get("name", "Unknown"),
                    "rating": place.get("rating", "N/A"),
                    "total_ratings": place.get("user_ratings_total", 0),
                    "address": place.get("vicinity", "Unknown location"),
                    "travel_time_mins": travel_time_mins,
                    "type": place.get("type", top_interest)
                })
            except Exception as e:
                logger.error(f"Error enriching place: {str(e)}")
                continue

        if not enriched_places:
            return None, "We couldn't enrich any places to recommend."

        # Construct LLM prompt
        feedback_note = user_feedback + " " if user_feedback else ""
        prompt = f"""
{feedback_note}You're a smart assistant helping a user decide which is the best place to visit.

User preferences:
- Weather: {user.get("weather", "Unknown")}
- Time: {user.get("current_time", "Unknown")}
- Top interest: {top_interest}
- Free hours: {user.get("free_hours", "Unknown")}

User History and Preferences:
{personalized_context}

Here are some options nearby:
"""

        for place in enriched_places:
            prompt += f"\n{place['prominence_rank']}. {place['name']} - Located at {place['address']}. "
            prompt += f"Rating: {place['rating']} ({place['total_ratings']} reviews). "
            prompt += f"Round trip travel time: {place['travel_time_mins']} minutes."

        prompt += """
❗ Choose only one place. Do not list or compare options. 
Make your response in 1–2 short, fun, personal sentences that could show up on a phone lockscreen.
Mention only one place by name.
"""

        response = model.generate_content(prompt)
        description = response.text.strip()

        # Extract the name of the place mentioned from the response
        selected_place = enriched_places[0]["place"]  # Default fallback

        for place in enriched_places:
            if place["name"].lower() in description.lower():
                selected_place = place["place"]
                break

        return selected_place, description

    except LLMError as e:
        logger.error(f"LLM Error in choose_place: {str(e)}")
        return None, "Sorry, we had an issue generating personalized recommendations. Let's try an indoor activity instead."
    except Exception as e:
        logger.error(f"Error in choose_place: {str(e)}")
        return None, "We encountered an unexpected error. Let's suggest an indoor activity instead."
