import streamlit as st
import os
from datetime import datetime
import google.generativeai as genai
import logging
import traceback

# Import from utils.py
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
    extract_keywords_from_prompt,  # New import
    extract_food_keywords,  # New import
    extract_nouns,  # New import
    fetch_image_for_keyword,
    fetch_unsplash_image,  # New import
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
                    image_url = None
                    main_keyword = None
                    
                    try:
                        # First, try to extract keywords using the advanced method
                        try:
                            keywords = extract_keywords_from_prompt(activity_description)
                            
                            # Try each keyword until we find an image
                            for keyword in keywords:
                                if not keyword or len(keyword.strip()) < 3:
                                    continue
                                    
                                logging.info(f"Trying to fetch image for keyword: {keyword}")
                                try:
                                    # Try Google Maps API first
                                    img_url = fetch_image_for_keyword(keyword, st.session_state.GOOGLE_MAPS_API_KEY)
                                    if img_url:
                                        image_url = img_url
                                        main_keyword = keyword
                                        logging.info(f"Found image for keyword: {keyword}")
                                        break
                                except Exception as img_err:
                                    logging.error(f"Error fetching image for '{keyword}': {str(img_err)}")
                                    continue
                        except Exception as kw_err:
                            logging.error(f"Error extracting keywords: {str(kw_err)}")
                            
                        # If still no image, try with the backup method
                        if not image_url:
                            # Fall back to simple extraction
                            main_keyword = extract_main_keywords(activity_description)
                            if main_keyword and len(main_keyword) >= 3:
                                logging.info(f"Trying fallback keyword: {main_keyword}")
                                image_url = fetch_image_for_keyword(main_keyword, st.session_state.GOOGLE_MAPS_API_KEY)
                            
                        # Final direct fallback to Unsplash
                        if not image_url and main_keyword:
                            logging.info(f"Trying direct Unsplash fetch for: {main_keyword}")
                            image_url = fetch_unsplash_image(main_keyword)
                            
                        # Last resort - try with the interest type
                        if not image_url:
                            logging.info(f"Using interest type as keyword: {top_interest}")
                            image_url = fetch_unsplash_image(top_interest)
                            main_keyword = top_interest
                            
                    except Exception as e:
                        logging.error(f"All image fetching methods failed: {str(e)}")
                        image_url = None
                        main_keyword = top_interest
            
                    # Debug logging
                    if image_url:
                        logging.info(f"Successfully found image URL: {image_url} for keyword: {main_keyword}")
                    else:
                        logging.error("Failed to find any image URL")
            
                    st.session_state.recommendation_data = {
                        "type": "indoor",
                        "name": f"Indoor {top_interest} Activity",
                        "description": activity_description,
                        "image_url": image_url,
                        "activity_type": top_interest,
                        "keyword": main_keyword if main_keyword else top_interest
                    }
                except Exception as e:
                    logging.error(f"Error in indoor flow: {str(e)}")
                    traceback.print_exc()
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
                        "image_url": None,
                        "activity_type": "activity"
                    }
                    st.session_state.errors.append(f"Error creating outdoor suggestion: {str(e)}")

            # Reset user feedback after using it
            if st.session_state.user_feedback:
                st.session_state.previous_feedback = st.session_state.user_feedback
                st.session_state.user_feedback = None

            st.session_state.recommendation_shown = True

        except Exception as e:
            logging.error(f"Unexpected error in recommendation process: {str(e)}")
            traceback.print_exc()
            st.session_state.errors.append(f"Unexpected error: {str(e)}")
            # Set up a basic fallback recommendation
            st.session_state.recommendation_data = {
                "type": "indoor",
                "name": "Activity Suggestion",
                "description": "Try something relaxing or fun based on your interests!",
                "image_url": None,
                "activity_type": "activity"
            }
            st.session_state.recommendation_shown = True

# Display the recommendation
if "recommendation_data" in st.session_state:
    data = st.session_state.recommendation_data

    # Display image if available (for both indoor and outdoor activities)
    if data.get("image_url"):
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
            # Update user preferences with like
            item_data = {
                "name": data.get("name", "Unknown"),
                "type": data.get("activity_type", "Unknown")
            }
            update_preferences_from_feedback("like", item_data)
            st.balloons()
            st.success("Great! I'll remember you liked this for future recommendations!")

    with col2:
        if st.button("👎 Show me something else"):
            # Update user preferences with dislike
            item_data = {
                "name": data.get("name", "Unknown"),
                "type": data.get("activity_type", "Unknown")
            }
            update_preferences_from_feedback("dislike", item_data)
            # Store feedback to use in next recommendation
            st.session_state.user_feedback = "The user did not like the previous suggestion. Please provide a completely different recommendation."
            st.session_state.recommendation_shown = False
            st.rerun()

    # Know More button
    if st.button("🔎 Tell me more"):
        # Update preferences when user views details
        item_data = {
            "name": data.get("name", "Unknown"),
            "type": data.get("activity_type", "Unknown")
        }
        update_preferences_from_feedback("view_details", item_data)

        # Get detailed suggestion
        detailed = get_detailed_suggestion(
            user,
            model,
            st.session_state.last_short_response,
            st.session_state.top_interest
        )
        st.markdown(f"### 📖 More details:\n\n{detailed}")

# Display errors if any occurred
if "errors" in st.session_state and st.session_state.errors:
    with st.expander("Troubleshooting Information", expanded=False):
        st.warning("Some issues occurred while generating your recommendations. We've provided alternatives instead.")
        for error in st.session_state.errors[-3:]:  # Show only the most recent errors
            st.error(error)
        if st.button("Clear Errors"):
            st.session_state.errors = []
            st.rerun()

# Display personalization summary in sidebar
with st.sidebar.expander("📊 Your Preference Profile"):
    prefs = get_user_preferences_db()

    # Show category preferences
    st.sidebar.subheader("Category Preferences")
    if prefs["category_preferences"]:
        for category, score in sorted(prefs["category_preferences"].items(), key=lambda x: x[1], reverse=True):
            st.sidebar.write(f"- {category}: {score:.1f}")
    else:
        st.sidebar.write("No preferences recorded yet.")

    # Show recent likes
    st.sidebar.subheader("Recent Likes")
    if prefs["liked_places"]:
        for item in prefs["liked_places"][-3:]:
            st.sidebar.write(f"- {item['name']} ({item['type']})")
    else:
        st.sidebar.write("No likes recorded yet.")

    # Show recent dislikes
    st.sidebar.subheader("Recent Dislikes")
    if prefs["disliked_places"]:
        for item in prefs["disliked_places"][-3:]:
            st.sidebar.write(f"- {item['name']} ({item['type']})")
    else:
        st.sidebar.write("No dislikes recorded yet.")

# Reset buttons
with st.sidebar.expander("🔄 Reset Options"):
    col1, col2 = st.sidebar.columns(2)

    with col1:
        if st.button("Reset Suggestion"):
            # Reset only current suggestion
            if "recommendation_shown" in st.session_state:
                del st.session_state.recommendation_shown
            if "recommendation_data" in st.session_state:
                del st.session_state.recommendation_data
            st.rerun()

    with col2:
        if st.button("Reset All"):
            # Reset everything including preferences
            for key in list(st.session_state.keys()):
                if key != "initialized" and key not in ["GOOGLE_MAPS_API_KEY", "model", "ors_client", "gmaps_client"]:
                    del st.session_state[key]
            st.rerun()

# Footer
st.sidebar.markdown("---")
st.sidebar.caption("Activity Planner App • v1.0")
