import datetime
import random
import pandas as pd
import openrouteservice
import googlemaps
import requests
import streamlit as st
import google.generativeai as genai
import os

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
            "travel": 0.93,
            "food": 0.81,
            "news": 0.65,
            "shopping": 0.58,
            "gaming": 0.76
        }
    }

# LLM Call 1 to fetch the top interest
def top_activity_interest_llm(user_context):
    model = st.session_state.model
    prompt = f"""
    You are a smart assistant that ranks user interests in the context of the moment.

    User Context:
    - City: {user_context['location']['city']}
    - Weather: {user_context['weather']}
    - Current Time: {user_context['current_time']}
    - Free Hours: {user_context['free_hours']}
    - Interests (with scores): {user_context['interests']}

    Based on this context, rank the categories from most to least relevant **for recommending an activity right now**.

    Return a ranked list like this:
    1. travel
    2. gaming
    3. shopping
    ...

    Only return the list — no explanations.
    """
    response = model.generate_content(prompt)
    ranked_categories = response.text.strip().split('\n')
    top_interest = ranked_categories[0].split(".")[1].strip() if ranked_categories else "travel"
    return top_interest

# LLM Call for Indoor or Outdoor Activity
def build_llm_decision_prompt(user_context, top_interest):
    return f"""
You are a smart activity recommender. Given the user's details below, decide whether to suggest an outdoor place or an indoor activity:
- Interest: {top_interest}
- Weather: {user_context['weather']}
- Time: {user_context['current_time']}
- Location: {user_context['location']['city']}
- Free hours: {user_context['free_hours']}

Reply with only one word: 'indoor' or 'outdoor'."""

# LLM Prompt for Indoor Activity
def build_llm_prompt_indoor(user_context, top_interest, user_feedback=None):
    feedback_note = "" if not user_feedback else f"{user_feedback} "
    
    prompt = f"""
{feedback_note}You are a personalized indoor activity planner.
User's top interest is: {top_interest}
Current weather: {user_context['weather']}
Time: {user_context['current_time']}
Free time available: {user_context['free_hours']} hours
Location: {user_context['location']['city']}

Suggest a single interesting indoor activity that suits the user's interest and context. Make it personal, fun, and specific to {top_interest}. Make the output 1–2 in short, fun, personal sentences that could show up on a phone lockscreen. Do not give any other output other than that.
"""
    return prompt

# Fetch places using Google Maps API
def fetch_places(user, top_interest, GOOGLE_MAPS_API_KEY):
    gmaps = googlemaps.Client(key=GOOGLE_MAPS_API_KEY)
    
    location = user.get("location", {})
    if not location or "lat" not in location or "lon" not in location:
        st.error("Location data is missing or incomplete.")
        return []

    lat, lon = location["lat"], location["lon"]
    
    # Map interests to place types
    interest_to_place_map = {
        "food": "restaurant",
        "travel": "tourist_attraction",
        "shopping": "shopping_mall",
        "sports": "stadium",
        "gaming": "arcade",
        "news": "library"
    }
    
    place_type = interest_to_place_map.get(top_interest.lower(), "point_of_interest")
    
    try:
        places_result = gmaps.places_nearby(
            location=(lat, lon),
            radius=20000,
            type=place_type,
            rank_by="prominence",
            open_now=True
        )
        
        # Filter places with photos and good ratings
        filtered_places = []
        for place in places_result.get("results", []):
            if place.get("photos") and place.get("user_ratings_total", 0) >= 20:
                filtered_places.append(place)
            if len(filtered_places) >= 5:
                break
                
        return filtered_places
    except Exception as e:
        st.error(f"Error fetching places: {e}")
        return []

# Fetch image for a place (if available)
def fetch_place_image(place, GOOGLE_MAPS_API_KEY):
    photos = place.get("photos")
    if photos and len(photos) > 0:
        photo_reference = photos[0].get("photo_reference")
        if photo_reference:
            return f"https://maps.googleapis.com/maps/api/place/photo?maxwidth=400&photoreference={photo_reference}&key={GOOGLE_MAPS_API_KEY}"
    return None

# Calculate travel time
def get_route_duration(from_coords, to_coords, ors_client):
    try:
        route = ors_client.directions(
            coordinates=[from_coords, to_coords],
            profile='driving-car',
            format='geojson'
        )
        duration_secs = route['features'][0]['properties']['summary']['duration']
        return round(duration_secs / 60, 1)  # Convert to minutes
    except:
        return None

# Choose one place using LLM
def choose_place(user, places, model, user_feedback=None):
    if not places:
        st.warning("No places found to choose from.")
        return None, "We couldn't find any interesting places nearby. Let's suggest an indoor activity instead."

    # Enrich place data
    enriched_places = []
    
    lat = user['location']['lat']
    lon = user['location']['lon']
    ors_client = st.session_state.ors_client
    
    for idx, place in enumerate(places[:3]):  # Limit to top 3 for brevity
        place_lat = place['geometry']['location']['lat']
        place_lon = place['geometry']['location']['lng']
        
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
            "travel_time_mins": travel_time_mins
        })

    # Include user feedback in the prompt if available
    feedback_note = "" if not user_feedback else f"{user_feedback} "
    
    # Create a prompt with summaries of the place options
    prompt = f"""
{feedback_note}You're a helpful assistant helping a user decide what to do next.

User preferences:
- Weather: {user.get("weather")}
- Time: {user.get("current_time")}
- Top interest: {st.session_state.top_interest}
- Free hours: {user.get("free_hours")}

Here are some options nearby:
"""

    for place in enriched_places:
        prompt += f"\n{place['prominence_rank']}. {place['name']} - Located at {place['address']}. "
        prompt += f"Rating: {place['rating']} ({place['total_ratings']} reviews). "
        prompt += f"Round trip travel time: {place['travel_time_mins']} minutes. "

    prompt += """
Based on this context, choose the best one and explain why it's a good fit right now.
Make your response in 1-2 short, fun, personal sentences that could show up on a phone lockscreen. Do not give any other output other than why this place is the best for now.
"""

    try:
        response = model.generate_content(prompt)
        description = response.text.strip()
        
        # If user provided feedback, try to select a different place than before
        if user_feedback and "previous_place_id" in st.session_state:
            # Try to pick a different place
            for place in places:
                if place.get("place_id") != st.session_state.previous_place_id:
                    st.session_state.previous_place_id = place.get("place_id")
                    return place, description
        
        # Store the selected place ID for future reference
        if places and len(places) > 0:
            st.session_state.previous_place_id = places[0].get("place_id")
            
        return places[0], description
    except Exception as e:
        st.error(f"Error generating place suggestion: {e}")
        return None, "Sorry, we had trouble generating a suggestion."

# Generate detailed suggestion using LLM
def get_detailed_suggestion(user, model, last_short_response, top_interest):
    prompt = f"""
You are a helpful assistant.

The user was previously shown this short recommendation:
"{last_short_response}"

User details:
- Interest: {top_interest}
- Location: {user['location']['city']}
- Weather: {user['weather']}
- Time: {user['current_time']}
- Free time available: {user['free_hours']} hours

Now the user has clicked 'Know More'.

Please give a more detailed, engaging, and informative version of the recommendation above. Include 5-6 sentence at most. Add why it's a good fit based on the context, what to expect there, and optionally a fun tip.
"""
    response = model.generate_content(prompt)
    return response.text
