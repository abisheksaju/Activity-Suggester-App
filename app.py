import streamlit as st
import os
from dotenv import load_dotenv
from datetime import datetime
import google.generativeai as genai
from utils import (
    get_synthetic_user,
    fetch_places,
    fetch_place_image,
    choose_place,
    get_detailed_suggestion
)

# Load secrets
GOOGLE_MAPS_API_KEY = st.secrets["GOOGLE_MAPS_API_KEY"]
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
ORS_API_KEY = st.secrets["ORS_API_KEY"]

# Configure Gemini model
os.environ['GEMINI_API_KEY'] = st.secrets["GEMINI_API_KEY"]
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash")

import streamlit as st

st.set_page_config(page_title="Activity Suggester", layout="centered")
# Inject custom CSS to position the title at the top-right
st.markdown("""
    <style>
    .custom-title {
        position: absolute;
        top: 10px;
        right: 20px;
        font-size: 14px;
        color: gray;
    }
    </style>
    <div class="custom-title">MeTime Genie</div>
""", unsafe_allow_html=True)
st.title("MeTime Genie")

# Generate user context if not already in session
if "user" not in st.session_state:
    user = get_synthetic_user()
    st.session_state.user = user
else:
    user = st.session_state.user

if "last_short_response" not in st.session_state:
    st.session_state.last_short_response = None

if "top_interest" not in st.session_state:
    st.session_state.top_interest = None

if "place_data" not in st.session_state:
    # Call LLM to suggest top interest
    prompt = f"""
You are a helpful assistant.
User context:
- Location: {user['location']['city']}
- Weather: {user['weather']}
- Time: {user['current_time']}
- Interests: {user['interests']}
- Calendar: {user['calendar']}
- Free hours: {user['free_hours']}

Based on this, suggest ONE top activity that best suits them right now. Only return the one-word interest (e.g., museum, cafe, gym, cinema).
"""
    top_interest = model.generate_content(prompt).text.strip().lower()
    st.session_state.top_interest = top_interest

    # Fetch places from Google Maps
    places = fetch_places(user, top_interest, GOOGLE_MAPS_API_KEY)

    # Choose one
    selected_place, description = choose_place(user, places, model)

    image_url = fetch_place_image(selected_place, GOOGLE_MAPS_API_KEY)

    st.session_state.place_data = {
        "place": selected_place,
        "description": description,
        "image_url": image_url
    }

# Display the suggested place
place_data = st.session_state.place_data
st.image(place_data["image_url"], use_column_width=True)
st.subheader("🔍 Suggested Activity")
st.write(place_data["description"])

st.session_state.last_short_response = place_data["description"]

# Know More button
if st.button("Know More"):
    detailed = get_detailed_suggestion(
        user,
        model,
        st.session_state.last_short_response,
        st.session_state.top_interest
    )
    st.markdown(f"### 📖 Here's more about your activity:\n\n{detailed}")

# Swipe to next button
if st.button("Show Another Suggestion"):
    if "place_data" in st.session_state:
        del st.session_state.place_data
