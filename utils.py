# This is the complete utils.py file

import datetime
import random
import pandas as pd
import openrouteservice
import googlemaps
import requests
import streamlit as st
import google.generativeai as genai
import os
import json
from pathlib import Path
import traceback
import logging
import re
from PIL import UnidentifiedImageError

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('activity_suggester')

# Custom exception classes
class AppError(Exception):
    """Base exception class for application errors"""
    def __init__(self, message, error_type="general", original_exception=None):
        self.message = message
        self.error_type = error_type
        self.original_exception = original_exception
        super().__init__(self.message)

class APIError(AppError):
    """Exception raised for errors in the API calls"""
    def __init__(self, message, api_name, original_exception=None):
        super().__init__(message, f"api_{api_name.lower()}", original_exception)
        self.api_name = api_name

class LLMError(AppError):
    """Exception raised for errors in LLM processing"""
    def __init__(self, message, original_exception=None):
        super().__init__(message, "llm_error", original_exception)

class ImageError(AppError):
    """Exception raised for errors in image handling"""
    def __init__(self, message, original_exception=None):
        super().__init__(message, "image_error", original_exception)

def safe_api_call(func):
    """Decorator for safely calling API functions"""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            api_name = func.__name__
            error_msg = f"Error in {api_name}: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            raise APIError(error_msg, api_name, e)
    return wrapper

# Set up clients
def init_clients(openroute_api_key, google_maps_api_key):
    ors_client = openrouteservice.Client(key=openroute_api_key)
    gmaps_client = googlemaps.Client(key=google_maps_api_key)
    return ors_client, gmaps_client

# Generate synthetic user context
def get_synthetic_user():
    # This is a placeholder function that returns synthetic user data
    # In a real app, you would get this data from the user's actual context
    return {
        "location": {
            "city": "Bangalore",
            "lat": 12.9716,
            "lon": 77.5946
        },
        "weather": "Cloudy",
        "current_time": "Saturday 3 PM",
        "free_hours": 4,
        "calendar": [
            {"event": "Lunch with friend", "start": "1 PM", "end": "2 PM"},
            {"event": "Office Meeting", "start": "4 PM", "end": "6:30 PM"}
        ],
        "interests": {
            "travel": 0.81,
            "food": 0.93,
            "news": 0.65,
            "shopping": 0.48,
            "gaming": 0.76
        }
    }

def extract_main_keywords(text):
    """
    Extract main keywords from indoor activity description
    """
    try:
        # If the text is empty or None, return a generic keyword
        if not text:
            return "indoor activity"

        # List of food and activity keywords to look for
        food_keywords = [
            "dosa", "cooking", "baking", "food", "recipe", "cuisine", "dish",
            "meal", "restaurant", "café", "bakery", "pizza", "burger", "pasta",
            "sushi", "curry", "breakfast", "lunch", "dinner", "snack",
            "dessert", "coffee", "tea", "smoothie", "cocktail", "pasta", "truffles"
        ]

        activity_keywords = [
            "yoga", "meditation", "painting", "drawing", "art", "craft",
            "reading", "book", "game", "gaming", "movie", "film", "music",
            "dance", "workout", "exercise", "pottery", "chess", "board game",
            "puzzle", "knitting", "photography", "baking", "cooking"
        ]

        # Combine all keywords
        all_keywords = food_keywords + activity_keywords

        # Convert to lowercase for case-insensitive matching
        text_lower = text.lower()

        # Find matching keywords
        matches = []
        for keyword in all_keywords:
            if keyword in text_lower:
                matches.append(keyword)

        # If we found any matches, return the longest one (likely most specific)
        if matches:
            return max(matches, key=len)

        # If no specific matches, use regex to find nouns (imperfect but useful fallback)
        words = re.findall(r'\b[A-Za-z]{4,}\b', text)
        if words:
            # Return the longest word as a fallback
            return max(words, key=len)

        # Last resort
        return "indoor activity"

    except Exception as e:
        logger.error(f"Error extracting keywords: {str(e)}")
        return "indoor activity"  # Fallback

def extract_keywords_from_prompt(prompt):
    """
    Extract keywords dynamically using OpenAI (or any LLM)
    Fallback: extract nouns with spaCy or basic split.
    """
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": "You're a helpful assistant that extracts 2-3 most important keywords from a user prompt, ideally nouns or phrases relevant for image search.",
                },
                {"role": "user", "content": f"Extract keywords from: {prompt}"},
            ],
            temperature=0.3,
        )
        keywords_text = response["choices"][0]["message"]["content"].strip()
        # Expecting comma-separated string of keywords
        keywords = [kw.strip() for kw in keywords_text.split(",")]
        return keywords

    except Exception as e:
        print(f"Keyword extraction failed: {e}")
        # Fallback: return first 3 significant words
        return prompt.split()[:3]
        
@safe_api_call
def fetch_image_for_keyword(keyword, GOOGLE_MAPS_API_KEY):
    """
    Fetch an image for a specific keyword using Google Places API
    """
    try:
        if not keyword:
            return None

        gmaps = googlemaps.Client(key=GOOGLE_MAPS_API_KEY)

        # Search for places related to the keyword
        places_result = gmaps.places(
            query=keyword,
            language="en",
        )

        # Filter places with photos
        places_with_photos = [place for place in places_result.get("results", [])
                             if place.get("photos")]

        if not places_with_photos:
            logger.warning(f"No photos found for keyword: {keyword}")
            return None

        # Select a random place with photos
        selected_place = random.choice(places_with_photos)

        # Get the photo reference
        photo_reference = selected_place["photos"][0]["photo_reference"]

        # Build the URL for the photo
        image_url = f"https://maps.googleapis.com/maps/api/place/photo?maxwidth=400&photoreference={photo_reference}&key={GOOGLE_MAPS_API_KEY}"

        return image_url

    except Exception as e:
        logger.error(f"Error fetching image for keyword '{keyword}': {str(e)}")
        raise ImageError(f"Could not fetch image for {keyword}", e)

def top_activity_interest_llm(user):
    """
    Use LLM to determine what activity would most interest the user right now
    """
    try:
        # For the MVP version we'll just use the top interest from the user profile
        if user and "interests" in user:
            interests = user["interests"]
            # Return the highest-scoring interest
            if interests:
                top_interest = max(interests.items(), key=lambda x: x[1])[0]
                return top_interest
        return "food"  # Default fallback
    except Exception as e:
        logger.error(f"Error determining top interest: {str(e)}")
        return "food"  # Default fallback

def build_llm_decision_prompt(user, top_interest):
    """
    Build a prompt to decide between indoor and outdoor activity
    """
    weather = user.get("weather", "Unknown")
    time = user.get("current_time", "Unknown")
    
    prompt = f"""
    Based on this context, decide if I should suggest an indoor or outdoor activity.
    Just respond with "indoor" or "outdoor".
    
    User context:
    - Current weather: {weather}
    - Current time: {time}
    - Their top interest: {top_interest}
    - Free hours: {user.get("free_hours", "Unknown")}
    
    Consider:
    - If it's late evening, raining, or very hot, indoor might be better
    - If it's morning or daytime with good weather, outdoor might be better
    - Also consider the interest - some activities like gaming are typically indoor
    """
    return prompt.strip()

def build_llm_prompt_indoor(user, top_interest, user_feedback=None):
    """
    Build a prompt for indoor activity suggestion
    """
    # Include user feedback if available
    feedback_note = "" if not user_feedback else f"{user_feedback} "
    
    prompt = f"""
    {feedback_note}Suggest a specific indoor activity related to {top_interest} that I can do at home or nearby.
    
    My context:
    - Current time: {user.get("current_time", "Unknown")}
    - I have {user.get("free_hours", "Unknown")} free hours
    - My top interest right now: {top_interest}
    
    Make your response 1-2 short, fun, personal sentences that help me decide what to do right now.
    Be specific and practical. Recommend something realistic, not generic.
    """
    return prompt.strip()

@safe_api_call
def fetch_places(user, interest_type, api_key):
    """
    Fetch places from Google Maps Places API based on user context and interest
    """
    try:
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
            'gaming': 'amusement_park'
        }
        
        # Get place type from interest
        place_type = place_type_mapping.get(interest_type, 'point_of_interest')
        
        # Search for places
        places_result = gmaps.places_nearby(
            location=(lat, lon),
            radius=3000,  # 3km radius
            type=place_type,
            open_now=True
        )
        
        return places_result.get('results', [])
    except Exception as e:
        logger.error(f"Error fetching places: {str(e)}")
        return []

def build_personalized_context(user, top_interest):
    """
    Build personalized context string based on user preferences
    """
    try:
        # Get user preferences from database (or default to empty)
        prefs = get_user_preferences_db()
        
        context = []
        
        # Add information about category preferences
        if prefs["category_preferences"]:
            top_categories = sorted(
                prefs["category_preferences"].items(), 
                key=lambda x: x[1], 
                reverse=True
            )[:3]
            
            categories_text = ", ".join([f"{cat} ({score:.1f})" for cat, score in top_categories])
            context.append(f"Top categories: {categories_text}")
        
        # Add information about liked places
        if prefs["liked_places"]:
            recent_likes = [item['name'] for item in prefs["liked_places"][-3:]]
            context.append(f"Recently liked: {', '.join(recent_likes)}")
        
        # Add information about disliked places
        if prefs["disliked_places"]:
            recent_dislikes = [item['name'] for item in prefs["disliked_places"][-3:]]
            context.append(f"Recently disliked: {', '.join(recent_dislikes)}")
        
        # Return the combined context
        if context:
            return "\n- " + "\n- ".join(context)
        return "No preference history available."
    except Exception as e:
        logger.error(f"Error building personalized context: {str(e)}")
        return "No preference history available."

@safe_api_call
def get_route_duration(origin, destination, ors_client):
    """
    Get the route duration between two points using OpenRouteService
    Returns time in minutes
    """
    try:
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
    except Exception as e:
        logger.error(f"Error getting route duration: {str(e)}")
        return None

@safe_api_call
def fetch_place_image(place, api_key):
    """
    Fetch an image for a place using Google Places API
    """
    try:
        if not place or 'photos' not in place or not place['photos']:
            return None
        
        # Get the photo reference
        photo_reference = place['photos'][0]['photo_reference']
        
        # Build the URL for the photo
        image_url = f"https://maps.googleapis.com/maps/api/place/photo?maxwidth=400&photoreference={photo_reference}&key={api_key}"
        
        return image_url
    except Exception as e:
        logger.error(f"Error fetching place image: {str(e)}")
        return None

def get_detailed_suggestion(user, model, short_description, interest_type):
    """
    Get detailed information about a suggestion
    """
    try:
        prompt = f"""
        Please provide more detailed information about this activity suggestion:
        "{short_description}"
        
        The user's main interest is: {interest_type}
        Current time: {user.get("current_time", "Unknown")}
        Free hours: {user.get("free_hours", "Unknown")}
        
        Provide 3-4 paragraphs with:
        1. More details about this specific activity
        2. Why it's a good fit for the user now
        3. Specific things to look for or enjoy
        
        Be specific, practical and personal. Make it sound exciting but realistic.
        """
        
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        logger.error(f"Error getting detailed suggestion: {str(e)}")
        return "I'm sorry, I couldn't generate additional details right now."

# User preferences functions
def get_user_preferences_db():
    """
    Get user preferences from "database" (session state in this MVP)
    """
    if "user_preferences" not in st.session_state:
        st.session_state.user_preferences = {
            "category_preferences": {
                "food": 0.5,
                "travel": 0.5,
                "shopping": 0.5,
                "gaming": 0.5,
                "news": 0.5
            },
            "liked_places": [],
            "disliked_places": []
        }
    
    return st.session_state.user_preferences

def update_preferences_from_feedback(feedback_type, item_data):
    """
    Update user preferences based on feedback
    """
    prefs = get_user_preferences_db()
    
    # Add to liked or disliked places
    if feedback_type == "like":
        prefs["liked_places"].append(item_data)
        
        # Increase category preference
        category = item_data.get("type", "")
        if category in prefs["category_preferences"]:
            prefs["category_preferences"][category] = min(
                1.0, prefs["category_preferences"][category] + 0.1
            )
            
    elif feedback_type == "dislike":
        prefs["disliked_places"].append(item_data)
        
        # Decrease category preference
        category = item_data.get("type", "")
        if category in prefs["category_preferences"]:
            prefs["category_preferences"][category] = max(
                0.1, prefs["category_preferences"][category] - 0.1
            )
            
    elif feedback_type == "view_details":
        # Slightly increase category preference when viewing details
        category = item_data.get("type", "")
        if category in prefs["category_preferences"]:
            prefs["category_preferences"][category] = min(
                1.0, prefs["category_preferences"][category] + 0.05
            )
    
    # Trim lists if they get too long
    if len(prefs["liked_places"]) > 20:
        prefs["liked_places"] = prefs["liked_places"][-20:]
    if len(prefs["disliked_places"]) > 20:
        prefs["disliked_places"] = prefs["disliked_places"][-20:]
    
    # Save back to session state
    st.session_state.user_preferences = prefs

# Enhanced version of choose_place with better error handling
@safe_api_call
def choose_place(user, places, model, user_feedback=None):
    """Choose place with comprehensive error handling"""
    if not places:
        logger.warning("No places found to choose from")
        return None, "We couldn't find any interesting places nearby. Let's suggest an indoor activity instead."

    try:
        # Enrich place data
        enriched_places = []

        lat = user.get('location', {}).get('lat')
        lon = user.get('location', {}).get('lon')

        if not lat or not lon:
            logger.warning("Missing user location coordinates")
            return None, "We couldn't determine your location accurately. Let's suggest an indoor activity instead."

        ors_client = st.session_state.get('ors_client')
        if not ors_client:
            logger.warning("Missing OpenRouteService client")
            return None, "We're having trouble with our navigation service. Let's suggest an indoor activity instead."

        # Get personalized context
        top_interest = st.session_state.get('top_interest', 'activity')
        personalized_context = build_personalized_context(user, top_interest)

        for idx, place in enumerate(places[:3]):  # Limit to top 3 for brevity
            try:
                place_lat = place.get('geometry', {}).get('location', {}).get('lat')
                place_lon = place.get('geometry', {}).get('location', {}).get('lng')

                if not place_lat or not place_lon:
                    logger.warning(f"Missing coordinates for place: {place.get('name', 'Unknown')}")
                    continue

                travel_time_mins = get_route_duration((lon, lat), (place_lon, place_lat), ors_client)
                if travel_time_mins:
                    travel_time_mins *= 2  # Round trip
                else:
                    travel_time_mins = "unknown"

                enriched_places.append({
                    "prominence_rank": idx + 1,
                    "name": place.get("name", "Unknown place"),
                    "rating": place.get("rating", "N/A"),
                    "total_ratings": place.get("user_ratings_total", 0),
                    "address": place.get("vicinity", "Unknown location"),
                    "travel_time_mins": travel_time_mins,
                    "type": place.get("type", top_interest)
                })
            except Exception as e:
                logger.error(f"Error enriching place {place.get('name', 'Unknown')}: {str(e)}")
                # Continue with next place

        if not enriched_places:
            return None, "We're having trouble processing places near you. Let's suggest an indoor activity instead."

        # Include user feedback in the prompt if available
        feedback_note = "" if not user_feedback else f"{user_feedback} "

        # Create a prompt with summaries of the place options
        prompt = f"""
{feedback_note}You're a helpful assistant helping a user decide what to do next.

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
            prompt += f"Round trip travel time: {place['travel_time_mins']} minutes. "

        prompt += """
Based on this context and the user's preferences history, choose the best one and explain why it's a good fit right now.
Make your response 1-2 short, fun, personal sentences that could show up on a phone lockscreen.
"""

        response = model.generate_content(prompt)
        description = response.text.strip()

        # If user provided feedback, try to select a different place than before
        if user_feedback and "previous_place_id" in st.session_state:
            # Try to pick a different place
            for place in places:
                if place.get("place_id") != st.session_state.previous_place_id:
                    st.session_state.previous_place_id = place.get("place_id")
                    # Add enrichment data
                    place.update({"description": description})
                    return place, description

        # Store the selected place ID for future reference
        if places and len(places) > 0:
            st.session_state.previous_place_id = places[0].get("place_id")
            # Add enrichment data
            places[0].update({"description": description})
            return places[0], description

    except LLMError as e:
        logger.error(f"LLM Error in choose_place: {str(e)}")
        return None, "Sorry, we had an issue generating personalized recommendations. Let's try an indoor activity instead."
    except Exception as e:
        logger.error(f"Error in choose_place: {str(e)}")
        logger.error(traceback.format_exc())
        return None, "We encountered an unexpected error. Let's suggest an indoor activity instead."

    return None, "Sorry, we had trouble generating a suggestion."
