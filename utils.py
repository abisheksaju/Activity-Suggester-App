import datetime
import random
import pandas as pd
import openrouteservice
import googlemaps
import requests
import streamlit as st

# Set up clients
def init_clients(openroute_api_key, google_maps_api_key):
    ors_client = openrouteservice.Client(key=openroute_api_key)
    gmaps_client = googlemaps.Client(key=google_maps_api_key)
    return ors_client, gmaps_client

# Generate synthetic user context
def get_synthetic_user():
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
            {"event": "Call with mom", "start": "6 PM", "end": "6:30 PM"}
        ],
        "interests": ["food", "music", "books", "nature"]
    }

# Fetch places using Google Maps API
def fetch_places(user, top_interest, GOOGLE_MAPS_API_KEY):
    import googlemaps
    import streamlit as st

    location = user.get("location", {})
    st.write("DEBUG: location =", location)  # helpful for debugging

    if not location or "lat" not in location or "lon" not in location:
        st.error("Location data is missing or incomplete.")
        return []

    lat, lon = location["lat"], location["lon"]
    gmaps = googlemaps.Client(key=GOOGLE_MAPS_API_KEY)

    try:
        places_result = gmaps.places_nearby(
            location=(lat, lon),
            radius=5000,
            keyword=top_interest
        )
        places = places_result.get("results", [])
        return places
    except Exception as e:
        st.error(f"Error fetching places: {e}")
        return []


# Fetch image for a place (if available)
def fetch_place_image(place, gmaps_client):
    photos = place.get("photos")
    if photos:
        photo_reference = photos[0]["photo_reference"]
        return f"https://maps.googleapis.com/maps/api/place/photo?maxwidth=400&photoreference={photo_reference}&key={gmaps_client.key}"
    return None

# Choose one place randomly
def choose_place(places):
    if not places:
        return None
    return random.choice(places)

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

Please give a more detailed, engaging, and informative version of the recommendation above. Include 2–3 paragraphs at most. Add why it’s a good fit based on the context, what to expect there, and optionally a fun tip.
"""
    response = model.generate_content(prompt)
    st.markdown(f"### Here's more about your activity:\n\n{response.text}")
    return response.text
