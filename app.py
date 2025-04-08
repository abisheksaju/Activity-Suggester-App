import streamlit as st
import os
from datetime import datetime
import google.generativeai as genai
from utils import (
    get_synthetic_user,
    top_activity_interest_llm,
    build_llm_decision_prompt,
    build_llm_prompt_indoor,
    fetch_places,
    fetch_place_image,
    choose_place,
    get_detailed_suggestion,
    init_clients
)

st.set_page_config(page_title="Activity Suggester", layout="centered")

# Inject custom CSS to position the title and improve UI
st.markdown("""
    <style>
    .custom-title {
        position: absolute;
        top: 10px;
        right: 20px;
        font-size: 14px;
        color: gray;
    }
    .stButton button {
        width: 100%;
        border-radius: 20px;
    }
    </style>
    <div class="custom-title">My Daily Activity Planner</div>
""", unsafe_allow_html=True)

# Initialize session state variables
if "initialized" not in st.session_state:
    # Load secrets
    try:
        GOOGLE_MAPS_API_KEY = st.secrets["GOOGLE_MAPS_API_KEY"]
        GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
        ORS_API_KEY = st.secrets["ORS_API_KEY"]
        
        # Configure Gemini model
        os.environ['GEMINI_API_KEY'] = GEMINI_API_KEY
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.0-flash")
        
        # Initialize clients
        ors_client, gmaps_client = init_clients(ORS_API_KEY, GOOGLE_MAPS_API_KEY)
        
        # Store in session state
        st.session_state.GOOGLE_MAPS_API_KEY = GOOGLE_MAPS_API_KEY
        st.session_state.model = model
        st.session_state.ors_client = ors_client
        st.session_state.gmaps_client = gmaps_client
        st.session_state.user_feedback = None
        st.session_state.initialized = True
    except Exception as e:
        st.error(f"Error initializing app: {e}")
        st.stop()

# Get model from session state
model = st.session_state.model

# App Header
st.title("What should I do now?")

# Generate user context if not already in session
if "user" not in st.session_state:
    user = get_synthetic_user()
    st.session_state.user = user
else:
    user = st.session_state.user

# Process recommendation when needed
if "recommendation_shown" not in st.session_state or not st.session_state.recommendation_shown:
    with st.spinner("Finding the perfect activity for you..."):
        # Call LLM to suggest top interest
        if "top_interest" not in st.session_state:
            top_interest = top_activity_interest_llm(user)
            st.session_state.top_interest = top_interest
        else:
            top_interest = st.session_state.top_interest
        
        # Call second LLM to decide indoor or outdoor
        decision_prompt = build_llm_decision_prompt(user, top_interest)
        decision_response = model.generate_content(decision_prompt)
        decision = decision_response.text.strip().lower()
        st.session_state.activity_type = decision
        
        # Indoor flow
        if decision == "indoor":
            # Pass user feedback to the LLM if available
            response = model.generate_content(build_llm_prompt_indoor(user, top_interest, st.session_state.user_feedback))
            st.session_state.last_short_response = response.text.strip()
            st.session_state.recommendation_data = {
                "type": "indoor",
                "description": response.text.strip(),
                "image_url": None
            }
        # Outdoor flow
        else:
            # Fetch places from Google Maps
            places = fetch_places(user, top_interest, st.session_state.GOOGLE_MAPS_API_KEY)
            
            # Choose one - pass user feedback to the LLM
            selected_place, description = choose_place(user, places, model, st.session_state.user_feedback)
            if selected_place:
                image_url = fetch_place_image(selected_place, st.session_state.GOOGLE_MAPS_API_KEY)
                st.session_state.recommendation_data = {
                    "type": "outdoor",
                    "place": selected_place,
                    "description": description,
                    "image_url": image_url
                }
                st.session_state.last_short_response = description
            else:
                # Fallback to indoor if no outdoor places found
                response = model.generate_content(build_llm_prompt_indoor(user, top_interest, st.session_state.user_feedback))
                st.session_state.last_short_response = response.text.strip()
                st.session_state.recommendation_data = {
                    "type": "indoor",
                    "description": response.text.strip(),
                    "image_url": None
                }
        
        # Reset user feedback after using it
        if st.session_state.user_feedback:
            st.session_state.previous_feedback = st.session_state.user_feedback
            st.session_state.user_feedback = None
            
        st.session_state.recommendation_shown = True

# Display the recommendation
if "recommendation_data" in st.session_state:
    data = st.session_state.recommendation_data
    
    if data["type"] == "outdoor" and data.get("image_url"):
        st.image(data["image_url"], use_column_width=True)
    
    st.subheader("🔍 Suggested Activity")
    st.write(data["description"])
    
    # Show if this was based on previous feedback
    if "previous_feedback" in st.session_state and st.session_state.previous_feedback:
        st.info("This is a new suggestion based on your feedback.")
        st.session_state.previous_feedback = None
    
    # Action buttons
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("👍 I like it!"):
            st.balloons()
            st.success("Great! Have a wonderful time!")

    with col2:
        if st.button("👎 Show me something else"):
            # Store feedback to use in next recommendation
            st.session_state.user_feedback = "The user did not like the previous suggestion. Please provide a completely different recommendation."
            st.session_state.recommendation_shown = False
            st.experimental_rerun()
    
    # Know More button
    if st.button("🔎 Tell me more"):
        detailed = get_detailed_suggestion(
            user,
            model,
            st.session_state.last_short_response,
            st.session_state.top_interest
        )
        st.markdown(f"### 📖 More details:\n\n{detailed}")

# Reset button (for testing)
if st.sidebar.button("Reset App"):
    for key in list(st.session_state.keys()):
        if key != "initialized" and key not in ["GOOGLE_MAPS_API_KEY", "model", "ors_client", "gmaps_client"]:
            del st.session_state[key]
    st.rerun()

# Footer
st.sidebar.markdown("---")
st.sidebar.caption("Activity Planner App • v1.0")
