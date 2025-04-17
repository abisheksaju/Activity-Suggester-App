import streamlit as st
import os
from datetime import datetime
import google.generativeai as genai
import logging
import traceback

# Import from utils.py
from utils import (
    get_synthetic_user,
    get_synthetic_weekend_slots,
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
    fetch_google_images, extract_core_keyword, simplify_keyword,
    # New imports for suggestion history
    get_suggestion_history,
    is_duplicate_suggestion,
    add_to_suggestion_history,
    get_llm_prompt_with_history,
    calculate_free_time,
    parse_time_to_minutes,
    AppError, APIError, LLMError, ImageError
)
from utils import astra_manager


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
        model = genai.GenerativeModel("gemini-1.5-flash")

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

# Session State Initialization for Weekend Planner


# App Header
st.title("What should I do now?")

# Session State Initialization for Weekend Planner
if "weekend_initialized" not in st.session_state:
   # Get basic user data
   if "user" not in st.session_state:
       user = get_synthetic_user()
       st.session_state.user = user
   else:
       user = st.session_state.user
   
   # Get weekend slots
   weekend_slots = get_synthetic_weekend_slots()
    
   # Initialize weekend planning session state variables
   st.session_state.weekend_slots = weekend_slots
   st.session_state.booked_slots = {}
   st.session_state.current_view = "main"
   st.session_state.slot_recommendations = {}
   st.session_state.weekend_initialized = True


# View Management
if "current_view" not in st.session_state:
   st.session_state.current_view = "main"

# Determine which view to display based on current_view value
if st.session_state.current_view == "main":
   render_main_view()
elif st.session_state.current_view == "slot" and "selected_slot_id" in st.session_state:
   render_slot_recommendation(st.session_state.selected_slot_id)
elif st.session_state.current_view == "quick_glance":
   render_quick_glance_view()
else:
   # Fallback to main view if something is wrong
   st.session_state.current_view = "main"
   render_main_view()


def render_main_view():
   """
   Renders the main view of the weekend planner with the primary recommendation
   and buttons for time slots and quick glance.
   """
   # Get user data
   user = st.session_state.user
   
   # Check if primary recommendation exists, if not generate one
   if "primary_recommendation" not in st.session_state:
       with st.spinner("Finding the perfect activity for you..."):
           # Get top interest
           top_interest = top_activity_interest_llm(user)
           st.session_state.top_interest = top_interest
           
           # Decide indoor or outdoor
           decision_prompt = build_llm_decision_prompt(user, top_interest)
           decision_response = st.session_state.model.generate_content(decision_prompt)
           decision = decision_response.text.strip().lower()
           
           # Generate recommendation based on decision
           if decision == "indoor":
               # Generate indoor activity
               prompt = build_llm_prompt_indoor(user, top_interest)
               response = st.session_state.model.generate_content(prompt)
               activity_description = response.text.strip()
               
               # Get image for activity
               main_keyword = extract_main_keywords(activity_description)
               image_url = fetch_image_for_keyword(main_keyword, st.session_state.GOOGLE_MAPS_API_KEY)
               
               recommendation = {
                   "type": "indoor",
                   "name": f"Indoor {top_interest} Activity",
                   "description": activity_description,
                   "image_url": image_url,
                   "activity_type": top_interest
               }
           else:
               # Generate outdoor activity
               places = fetch_places(user, top_interest, st.session_state.GOOGLE_MAPS_API_KEY)
               selected_place, description = choose_place(user, places, st.session_state.model)
               
               if selected_place:
                   image_url = fetch_place_image(selected_place, st.session_state.GOOGLE_MAPS_API_KEY)
                   recommendation = {
                       "type": "outdoor",
                       "place": selected_place,
                       "name": selected_place.get("name", "Unknown place"),
                       "description": description,
                       "image_url": image_url,
                       "activity_type": top_interest
                   }
               else:
                   # Fallback to indoor if no places found
                   prompt = build_llm_prompt_indoor(user, top_interest)
                   response = st.session_state.model.generate_content(prompt)
                   activity_description = response.text.strip()
                   main_keyword = extract_main_keywords(activity_description)
                   image_url = fetch_image_for_keyword(main_keyword, st.session_state.GOOGLE_MAPS_API_KEY)
                   
                   recommendation = {
                       "type": "indoor",
                       "name": f"Indoor {top_interest} Activity",
                       "description": activity_description,
                       "image_url": image_url,
                       "activity_type": top_interest
                   }
           
           st.session_state.primary_recommendation = recommendation
           st.session_state.last_short_response = recommendation["description"]
   
   # Display primary recommendation
   recommendation = st.session_state.primary_recommendation
   
   # Display image if available
   if recommendation.get("image_url"):
       st.image(recommendation["image_url"], use_column_width=True)
   
   # Display recommendation details
   st.subheader("🔍 Suggested Activity")
   st.write(recommendation["description"])
   
   # Record interaction in database
   success = astra_manager.record_interaction({
       "user_id": user.get("user_id", "unknown"),
       "interaction_type": recommendation.get("type"),  # "indoor" or "outdoor"
       "suggested_activity": recommendation.get("description"),
       "recommendation_data": recommendation,  # full recommendation payload
       "user_action": "",  # placeholder for Like / Dislike / etc.
       "session_id": st.session_state.get("session_id"),
       "user_interests": user.get("interests", {}),
       "location": user.get("location", {}),
       "weather": user.get("weather", ""),
       "time": user.get("current_time", ""),
       "calendar": user.get("calendar", [])
   })

   if not success:
       st.warning("⚠️ Failed to save interaction to database.")
   
   # Action buttons for primary recommendation
   col1, col2 = st.columns(2)
   
   with col1:
       if st.button("👍 I like it!"):
           # Update user preferences with like
           item_data = {
               "name": recommendation.get("name", "Unknown"),
               "type": recommendation.get("activity_type", "Unknown")
           }
           update_preferences_from_feedback("like", item_data)
           st.balloons()
           st.success("Great! I'll remember you liked this!")
   
   with col2:
       if st.button("👎 Show me something else"):
           # Update user preferences with dislike
           item_data = {
               "name": recommendation.get("name", "Unknown"),
               "type": recommendation.get("activity_type", "Unknown")
           }
           update_preferences_from_feedback("dislike", item_data)
           
           # Clear primary recommendation to generate a new one
           if "primary_recommendation" in st.session_state:
               del st.session_state.primary_recommendation
           
           st.rerun()
   
   # Know More button
   if st.button("🔎 Tell me more"):
       # Update preferences when user views details
       item_data = {
           "name": recommendation.get("name", "Unknown"),
           "type": recommendation.get("activity_type", "Unknown")
       }
       update_preferences_from_feedback("view_details", item_data)
       
       # Get detailed suggestion
       detailed, maps_html = get_detailed_suggestion(
           user,
           st.session_state.model,
           st.session_state.last_short_response,
           st.session_state.top_interest,
           st.session_state.primary_recommendation
       )
       st.markdown(f"### 📖 More details:\n\n{detailed}")
       
       # Display maps link if available
       if maps_html:
           st.markdown(maps_html, unsafe_allow_html=True)
   
   # Book this slot button
   if st.button("📌 Book this slot"):
       # Find nearest slot in weekend slots (for demo, just use first slot)
       if st.session_state.weekend_slots and len(st.session_state.weekend_slots) > 0:
           nearest_slot = st.session_state.weekend_slots[0]
           slot_id = nearest_slot["id"]
           
           # Book the activity for this slot
           st.session_state.booked_slots[slot_id] = recommendation
           
           # Record interaction in database
           success = astra_manager.record_interaction({
               "user_id": user.get("user_id", "unknown"),
               "interaction_type": "booking",
               "slot_id": slot_id,
               "slot_day": nearest_slot["day"],
               "slot_time": f"{nearest_slot['start_time']} - {nearest_slot['end_time']}",
               "activity": recommendation,
               "timestamp": datetime.now().isoformat()
           })
           
           st.success(f"Activity booked for {nearest_slot['day']} {nearest_slot['start_time']} - {nearest_slot['end_time']}!")
   
   # Display weekend planning section
   st.markdown("---")
   st.subheader("Hey, I've planned exciting stuff for your weekend! Here's a quick glance!")
   
   # Display slot buttons
   st.markdown("### Choose a time slot:")
   
   # Create buttons for each time slot
   slot_cols = st.columns(min(len(st.session_state.weekend_slots), 4))
   
   for i, slot in enumerate(st.session_state.weekend_slots):
       slot_id = slot["id"]
       slot_text = f"{slot['day']} {slot['start_time']}-{slot['end_time']}"
       
       # Check if slot is booked
       is_booked = slot_id in st.session_state.booked_slots
       
       # Display slot button with appropriate styling
       with slot_cols[i % len(slot_cols)]:
           button_label = f"{slot_text}"
           if is_booked:
               button_label += " ✓"
           
           if st.button(button_label, key=f"slot_btn_{slot_id}"):
               st.session_state.selected_slot_id = slot_id
               st.session_state.current_view = "slot"
               st.rerun()
   
   # Quick Glance button
   if st.button("🔍 Quick Glance", key="quick_glance_btn"):
       st.session_state.current_view = "quick_glance"
       st.rerun()





def render_slot_recommendation(slot_id):
   """
   Renders the recommendation view for a specific time slot.
   
   Args:
       slot_id: ID of the selected slot (e.g., "S1", "S2")
   """
   # Get user data
   user = st.session_state.user
   
   # Get slot data
   slot = None
   for s in st.session_state.weekend_slots:
       if s["id"] == slot_id:
           slot = s
           break
   
   if not slot:
       st.error(f"Slot {slot_id} not found!")
       st.session_state.current_view = "main"
       st.rerun()
       return
   
   # Display slot information
   st.header(f"Activity for {slot['day']} {slot['start_time']}-{slot['end_time']}")
   
   # Check if this slot is already booked
   is_booked = slot_id in st.session_state.booked_slots
   
   if is_booked:
       # Display the booked activity
       recommendation = st.session_state.booked_slots[slot_id]
       st.success("✅ This slot is booked!")
   else:
       # Generate or retrieve recommendation for this slot
       if slot_id not in st.session_state.slot_recommendations:
           with st.spinner("Finding the perfect activity for this time slot..."):
               # Get top interest
               top_interest = top_activity_interest_llm(user)
               
               # Decide indoor or outdoor
               decision_prompt = build_llm_decision_prompt(user, top_interest)
               decision_response = st.session_state.model.generate_content(decision_prompt)
               decision = decision_response.text.strip().lower()
               
               # Generate recommendation based on decision
               if decision == "indoor":
                   # Build prompt with slot-specific context
                   slot_context = f"You have {slot['duration_hours']} hours available on {slot['day']} from {slot['start_time']} to {slot['end_time']}."
                   prompt = build_llm_prompt_indoor(user, top_interest)
                   # Insert slot context into prompt
                   prompt = prompt.replace("My context:", f"My context:\n- {slot_context}\n-")
                   
                   response = st.session_state.model.generate_content(prompt)
                   activity_description = response.text.strip()
                   
                   # Get image for activity
                   main_keyword = extract_main_keywords(activity_description)
                   image_url = fetch_image_for_keyword(main_keyword, st.session_state.GOOGLE_MAPS_API_KEY)
                   
                   recommendation = {
                       "type": "indoor",
                       "name": f"Indoor {top_interest} Activity",
                       "description": activity_description,
                       "image_url": image_url,
                       "activity_type": top_interest
                   }
               else:
                   # Generate outdoor activity
                   places = fetch_places(user, top_interest, st.session_state.GOOGLE_MAPS_API_KEY)
                   
                   # Add slot context for outdoor selection
                   slot_context = f"The user has {slot['duration_hours']} hours available on {slot['day']} from {slot['start_time']} to {slot['end_time']}."
                   selected_place, description = choose_place(user, places, st.session_state.model, user_feedback=slot_context)
                   
                   if selected_place:
                       image_url = fetch_place_image(selected_place, st.session_state.GOOGLE_MAPS_API_KEY)
                       recommendation = {
                           "type": "outdoor",
                           "place": selected_place,
                           "name": selected_place.get("name", "Unknown place"),
                           "description": description,
                           "image_url": image_url,
                           "activity_type": top_interest
                       }
                   else:
                       # Fallback to indoor if no outdoor places found
                       prompt = build_llm_prompt_indoor(user, top_interest)
                       # Insert slot context into prompt
                       prompt = prompt.replace("My context:", f"My context:\n- {slot_context}\n-")
                       
                       response = st.session_state.model.generate_content(prompt)
                       activity_description = response.text.strip()
                       main_keyword = extract_main_keywords(activity_description)
                       image_url = fetch_image_for_keyword(main_keyword, st.session_state.GOOGLE_MAPS_API_KEY)
                       
                       recommendation = {
                           "type": "indoor",
                           "name": f"Indoor {top_interest} Activity",
                           "description": activity_description,
                           "image_url": image_url,
                           "activity_type": top_interest
                       }
               
               # Store recommendation in session state
               st.session_state.slot_recommendations[slot_id] = recommendation
               st.session_state.last_short_response = recommendation["description"]
       
       # Get the recommendation from session state
       recommendation = st.session_state.slot_recommendations[slot_id]
   
   # Display recommendation
   if recommendation.get("image_url"):
       st.image(recommendation["image_url"], use_column_width=True)
   
   st.subheader("🔍 Suggested Activity")
   st.write(recommendation["description"])
   
   # Record interaction in database
   success = astra_manager.record_interaction({
       "user_id": user.get("user_id", "unknown"),
       "interaction_type": recommendation.get("type"),  # "indoor" or "outdoor"
       "suggested_activity": recommendation.get("description"),
       "recommendation_data": recommendation,  # full recommendation payload
       "user_action": "",  # placeholder for Like / Dislike / etc.
       "session_id": st.session_state.get("session_id"),
       "user_interests": user.get("interests", {}),
       "location": user.get("location", {}),
       "weather": user.get("weather", ""),
       "time": user.get("current_time", ""),
       "calendar": user.get("calendar", []),
       "slot_id": slot_id,
       "slot_info": slot
   })
   
   if not success:
       st.warning("⚠️ Failed to save interaction to database.")
   
   # Action buttons
   if not is_booked:
       # Show like/dislike buttons only if not booked
       col1, col2 = st.columns(2)
       
       with col1:
           if st.button("👍 I like it!", key=f"like_slot_{slot_id}"):
               # Update user preferences with like
               item_data = {
                   "name": recommendation.get("name", "Unknown"),
                   "type": recommendation.get("activity_type", "Unknown")
               }
               update_preferences_from_feedback("like", item_data)
               st.balloons()
               st.success("Great! I'll remember you liked this!")
       
       with col2:
           if st.button("👎 Show me something else", key=f"dislike_slot_{slot_id}"):
               # Update user preferences with dislike
               item_data = {
                   "name": recommendation.get("name", "Unknown"),
                   "type": recommendation.get("activity_type", "Unknown")
               }
               update_preferences_from_feedback("dislike", item_data)
               
               # Remove this recommendation to generate a new one
               if slot_id in st.session_state.slot_recommendations:
                   del st.session_state.slot_recommendations[slot_id]
               
               st.rerun()
       
       # Know More button
       if st.button("🔎 Tell me more", key=f"more_slot_{slot_id}"):
           # Update preferences when user views details
           item_data = {
               "name": recommendation.get("name", "Unknown"),
               "type": recommendation.get("activity_type", "Unknown")
           }
           update_preferences_from_feedback("view_details", item_data)
           
           # Get detailed suggestion
           detailed, maps_html = get_detailed_suggestion(
               user,
               st.session_state.model,
               recommendation["description"],
               recommendation.get("activity_type", ""),
               recommendation
           )
           st.markdown(f"### 📖 More details:\n\n{detailed}")
           
           # Display maps link if available
           if maps_html:
               st.markdown(maps_html, unsafe_allow_html=True)
       
       # Book this slot button
       if st.button("📌 Book this slot", key=f"book_slot_{slot_id}"):
           # Book the activity for this slot
           st.session_state.booked_slots[slot_id] = recommendation
           
           # Record interaction in database
           success = astra_manager.record_interaction({
               "user_id": user.get("user_id", "unknown"),
               "interaction_type": "booking",
               "slot_id": slot_id,
               "slot_day": slot["day"],
               "slot_time": f"{slot['start_time']} - {slot['end_time']}",
               "activity": recommendation,
               "timestamp": datetime.now().isoformat()
           })
           
           st.success(f"Activity booked for {slot['day']} {slot['start_time']} - {slot['end_time']}!")
           st.rerun()
   
   # Back to main view button
   if st.button("← Back to main view", key=f"back_slot_{slot_id}"):
       st.session_state.current_view = "main"
       st.rerun()






def render_quick_glance_view():
   """
   Renders the quick glance view showing all weekend slots with their recommended activities.
   """
   # Get user data
   user = st.session_state.user
   
   st.header("Your Weekend Plan - Quick Glance")
   
   # Ensure all slots have recommendations
   for slot in st.session_state.weekend_slots:
       slot_id = slot["id"]
       if slot_id not in st.session_state.slot_recommendations and slot_id not in st.session_state.booked_slots:
           with st.spinner(f"Finding an activity for {slot['day']} {slot['start_time']}-{slot['end_time']}..."):
               # Get top interest
               top_interest = top_activity_interest_llm(user)
               
               # Generate a recommendation (simplified for quick glance)
               prompt = build_llm_prompt_indoor(user, top_interest)
               slot_context = f"You have {slot['duration_hours']} hours available on {slot['day']} from {slot['start_time']} to {slot['end_time']}."
               prompt = prompt.replace("My context:", f"My context:\n- {slot_context}\n-")
               
               response = st.session_state.model.generate_content(prompt)
               activity_description = response.text.strip()
               
               # Get image (simplified)
               main_keyword = extract_main_keywords(activity_description)
               image_url = fetch_image_for_keyword(main_keyword, st.session_state.GOOGLE_MAPS_API_KEY)
               
               recommendation = {
                   "type": "indoor",
                   "name": f"{top_interest} Activity",
                   "description": activity_description,
                   "image_url": image_url,
                   "activity_type": top_interest
               }
               
               # Store in session state
               st.session_state.slot_recommendations[slot_id] = recommendation
   
   # Display all slots in a grid
   num_cols = 2  # Display 2 slots per row
   
   # Group slots by day
   saturday_slots = [slot for slot in st.session_state.weekend_slots if slot["day"] == "Saturday"]
   sunday_slots = [slot for slot in st.session_state.weekend_slots if slot["day"] == "Sunday"]
   
   # Display Saturday slots
   if saturday_slots:
       st.subheader("Saturday")
       rows = (len(saturday_slots) + num_cols - 1) // num_cols  # Ceiling division
       
       for row in range(rows):
           cols = st.columns(num_cols)
           for col_idx in range(num_cols):
               slot_idx = row * num_cols + col_idx
               if slot_idx < len(saturday_slots):
                   slot = saturday_slots[slot_idx]
                   slot_id = slot["id"]
                   
                   with cols[col_idx]:
                       # Get the recommendation for this slot
                       if slot_id in st.session_state.booked_slots:
                           recommendation = st.session_state.booked_slots[slot_id]
                           is_booked = True
                       elif slot_id in st.session_state.slot_recommendations:
                           recommendation = st.session_state.slot_recommendations[slot_id]
                           is_booked = False
                       else:
                           continue  # Skip if no recommendation (shouldn't happen)
                       
                       # Create a card-like UI
                       st.markdown(f"### {slot['start_time']}-{slot['end_time']}")
                       if is_booked:
                           st.success("✅ Booked")
                       
                       if recommendation.get("image_url"):
                           st.image(recommendation["image_url"], width=200)
                       
                       # Truncate description if too long
                       description = recommendation["description"]
                       if len(description) > 100:
                           description = description[:97] + "..."
                       st.write(description)
                       
                       # Make card clickable
                       if st.button("View Details", key=f"quickview_{slot_id}"):
                           st.session_state.selected_slot_id = slot_id
                           st.session_state.current_view = "slot"
                           st.rerun()
   
   # Display Sunday slots
   if sunday_slots:
       st.subheader("Sunday")
       rows = (len(sunday_slots) + num_cols - 1) // num_cols  # Ceiling division
       
       for row in range(rows):
           cols = st.columns(num_cols)
           for col_idx in range(num_cols):
               slot_idx = row * num_cols + col_idx
               if slot_idx < len(sunday_slots):
                   slot = sunday_slots[slot_idx]
                   slot_id = slot["id"]
                   
                   with cols[col_idx]:
                       # Get the recommendation for this slot
                       if slot_id in st.session_state.booked_slots:
                           recommendation = st.session_state.booked_slots[slot_id]
                           is_booked = True
                       elif slot_id in st.session_state.slot_recommendations:
                           recommendation = st.session_state.slot_recommendations[slot_id]
                           is_booked = False
                       else:
                           continue  # Skip if no recommendation (shouldn't happen)
                       
                       # Create a card-like UI
                       st.markdown(f"### {slot['start_time']}-{slot['end_time']}")
                       if is_booked:
                           st.success("✅ Booked")
                       
                       if recommendation.get("image_url"):
                           st.image(recommendation["image_url"], width=200)
                       
                       # Truncate description if too long
                       description = recommendation["description"]
                       if len(description) > 100:
                           description = description[:97] + "..."
                       st.write(description)
                       
                       # Make card clickable
                       if st.button("View Details", key=f"quickview_{slot_id}"):
                           st.session_state.selected_slot_id = slot_id
                           st.session_state.current_view = "slot"
                           st.rerun()
   
   # Back to main view button
   if st.button("← Back to main view", key="back_from_quickglance"):
       st.session_state.current_view = "main"
       st.rerun()







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
        st.sidebar.write("No likes recorded yet .")

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
