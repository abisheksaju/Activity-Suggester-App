import streamlit as st
import os
from datetime import datetime
import google.generativeai as genai
import logging
import traceback

# Import all functions from utils.py
from utils import (
    get_synthetic_user,
    top_activity_interest_llm,
    build_llm_decision_prompt,
    build_llm_prompt_indoor,
    fetch_places,
    fetch_place_image,
    choose_place,
    get_detailed_suggestion,
    init_clients,
    update_preferences_from_feedback,
    get_user_preferences_db,
    extract_main_keywords,
    fetch_image_for_keyword,
    AppError, APIError, LLMError, ImageError
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
    .feedback-history {
        margin-top: 30px;
        padding: 10px;
        background-color: #f5f5f5;
        border-radius: 5px;
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

        # Set up error tracking
        st.session_state.errors = []
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
        try:
            # Call LLM to suggest top interest
            if "top_interest" not in st.session_state:
                try:
                    top_interest = top_activity_interest_llm(user)
                    st.session_state.top_interest = top_interest
                except Exception as e:
                    logging.error(f"Error getting top interest: {str(e)}")
                    st.session_state.top_interest = "food"  # Default fallback
                    st.session_state.errors.append(f"Error determining interest: {str(e)}")
            else:
                top_interest = st.session_state.top_interest

            # Call second LLM to decide indoor or outdoor
            try:
                decision_prompt = build_llm_decision_prompt(user, top_interest)
                decision_response = model.generate_content(decision_prompt)
                decision = decision_response.text.strip().lower()
                st.session_state.activity_type = decision
            except Exception as e:
                logging.error(f"Error determining indoor/outdoor: {str(e)}")
                decision = "indoor"  # Default to indoor on error
                st.session_state.activity_type = decision
                st.session_state.errors.append(f"Error choosing activity type: {str(e)}")

            # Indoor flow
            if decision == "indoor":
                try:
                    response = model.generate_content(build_llm_prompt_indoor(user, top_interest, st.session_state.user_feedback))
                    activity_description = response.text.strip()
                    st.session_state.last_short_response = activity_description

                    # Extract keywords and fetch related image
                    main_keyword = extract_main_keywords(activity_description)
                    image_url = None

                    try:
                        if main_keyword:
                            image_url = fetch_image_for_keyword(main_keyword, st.session_state.GOOGLE_MAPS_API_KEY)
                    except Exception as e:
                        logging.error(f"Image search error: {str(e)}")
                        st.session_state.errors.append(f"Couldn't find a related image: {str(e)}")

                    st.session_state.recommendation_data = {
                        "type": "indoor",
                        "name": f"Indoor {top_interest} Activity",
                        "description": activity_description,
                        "image_url": image_url,  # This might be None if image fetch failed
                        "activity_type": top_interest,
                        "keyword": main_keyword  # Store the extracted keyword
                    }
                except Exception as e:
                    logging.error(f"Error in indoor flow: {str(e)}")
                    st.session_state.recommendation_data = {
                        "type": "indoor",
                        "name": "Indoor Activity Suggestion",
                        "description": "Try a fun indoor activity related to your interests!",
                        "image_url": None,
                        "activity_type": top_interest
                    }
                    st.session_state.errors.append(f"Error creating indoor suggestion: {str(e)}")
            # Outdoor flow
            else:
                try:
                    # Fetch places from Google Maps
                    places = fetch_places(user, top_interest, st.session_state.GOOGLE_MAPS_API_KEY)

                    # Choose one - pass user feedback to the LLM
                    selected_place, description = choose_place(user, places, model, st.session_state.user_feedback)
                    if selected_place:
                        try:
                            image_url = fetch_place_image(selected_place, st.session_state.GOOGLE_MAPS_API_KEY)
                        except Exception as e:
                            logging.error(f"Error fetching place image: {str(e)}")
                            image_url = None

                        st.session_state.recommendation_data = {
                            "type": "outdoor",
                            "place": selected_place,
                            "name": selected_place.get("name", "Unknown place"),
                            "description": description,
                            "image_url": image_url,
                            "activity_type": top_interest
                        }
                        st.session_state.last_short_response = description
                    else:
                        # Fallback to indoor if no outdoor places found
                        logging.warning("No outdoor places found, falling back to indoor")
                        response = model.generate_content(build_llm_prompt_indoor(user, top_interest, st.session_state.user_feedback))
                        activity_description = response.text.strip()

                        # Extract keywords and fetch related image
                        main_keyword = extract_main_keywords(activity_description)
                        image_url = None

                        try:
                            if main_keyword:
                                image_url = fetch_image_for_keyword(main_keyword, st.session_state.GOOGLE_MAPS_API_KEY)
                        except Exception as e:
                            logging.error(f"Error fetching indoor fallback image: {str(e)}")

                        st.session_state.last_short_response = activity_description
                        st.session_state.recommendation_data = {
                            "type": "indoor",
                            "name": f"Indoor {top_interest} Activity",
                            "description": activity_description,
                            "image_url": image_url,
                            "activity_type": top_interest,
                            "keyword": main_keyword
                        }
                except Exception as e:
                    logging.error(f"Error in outdoor flow: {str(e)}")
                    traceback.print_exc()
                    # Emergency fallback
                    st.session_state.recommendation_data = {
                        "type": "indoor",
                        "name": "Activity Suggestion",
                        "description": "We recommend trying something fun related to your interests!",
