import streamlit as st
import os
from datetime import datetime
import google.generativeai as genai
# Add this to the imports at the top of app.py
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
    extract_main_keywords,  # New import
    fetch_image_for_keyword,  # New import
    AppError, APIError, LLMError, ImageError  # New error classes
)
import logging
import traceback

# Add after initializing session state variables
# Set up error handling in the app
if "errors" not in st.session_state:
    st.session_state.errors = []

# Process recommendation when needed - update this section
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

                    # NEW CODE: Extract keywords and fetch related image
                    main_keyword = extract_main_keywords(activity_description)
                    image_url = None

                    try:
                        if main_keyword:
                            image_url = fetch_image_for_keyword(main_keyword, st.session_state.GOOGLE_MAPS_API_KEY)
                    except ImageError as e:
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

# Display errors if any occurred
if "errors" in st.session_state and st.session_state.errors:
    with st.expander("Troubleshooting Information", expanded=False):
        st.warning("Some issues occurred while generating your recommendations. We've provided alternatives instead.")
        for error in st.session_state.errors[-3:]:  # Show only the most recent errors
            st.error(error)
        if st.button("Clear Errors"):
            st.session_state.errors = []
            st.rerun()