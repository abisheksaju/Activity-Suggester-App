import streamlit as st
import os
from datetime import datetime
import google.generativeai as genai
import logging
import traceback
# Remove ChromaDB import
from langchain.globals import set_debug
import json

# Import from our modules
from activity_graph import ActivitySuggesterGraph
# from chroma_manager import ChromaManager  # Replace with JSONStorageManager
from json_storage_manager import JSONStorageManager  # New import
from image_utils import fetch_image_for_activity
from api_utils import init_clients, safe_api_call
from user_utils import get_synthetic_user, calculate_free_time
from config import SETTINGS

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('activity_suggester')

# Enable debug mode for LangChain
set_debug(True)

# Set page configuration
st.set_page_config(page_title="Activity Suggester", layout="centered")

# Inject custom CSS
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
    /* Tab content spacing */
    .stTabs [data-baseweb="tab-panel"] {
        padding-top: 1rem;
    }
    </style>
    <div class="custom-title">My Daily Activity Planner</div>
""", unsafe_allow_html=True)

# Initialize app state
def initialize_app():
    # Load API keys from secrets
    try:
        GOOGLE_MAPS_API_KEY = st.secrets.get("GOOGLE_MAPS_API_KEY", "demo_key")
        GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "demo_key")
        ORS_API_KEY = st.secrets.get("ORS_API_KEY", "demo_key")
        
        # Configure Gemini model
        os.environ['GEMINI_API_KEY'] = GEMINI_API_KEY
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-1.5-flash")
        
        # Initialize API clients
        ors_client, gmaps_client = init_clients(ORS_API_KEY, GOOGLE_MAPS_API_KEY)
        
        # Initialize JSONStorageManager instead of ChromaDB
        storage_manager = JSONStorageManager()
        
        # Initialize LangGraph
        activity_graph = ActivitySuggesterGraph(
            model=model,
            chroma_manager=storage_manager,  # Pass JSONStorageManager here
            api_keys={
                "google_maps": GOOGLE_MAPS_API_KEY,
                "ors": ORS_API_KEY
            }
        )
        
        # Store in session state
        st.session_state.model = model
        st.session_state.ors_client = ors_client
        st.session_state.gmaps_client = gmaps_client
        st.session_state.chroma_manager = storage_manager  # Keep variable name for compatibility
        st.session_state.activity_graph = activity_graph
        st.session_state.user_feedback = None
        st.session_state.errors = []
        
        # Set initialization flag
        st.session_state.initialized = True
        
        return True
    except Exception as e:
        st.error(f"Error initializing app: {str(e)}")
        st.error(traceback.format_exc())
        return False

# Check if app is initialized, if not, initialize it
if "initialized" not in st.session_state:
    if not initialize_app():
        st.stop()

# Main app title
st.title("What should I do now?")

# Tab for main recommendation and admin view
tabs = st.tabs(["Activity Recommendations", "Admin Dashboard"])

# Tab 1: Activity Recommendations
with tabs[0]:
    # Get user context (either from session or generate new)
    if "user" not in st.session_state:
        user = get_synthetic_user()
        st.session_state.user = user
        
        # Store user in storage if not already there
        storage_manager = st.session_state.chroma_manager  # Using the same session state key
        storage_manager.add_or_update_user(user["user_id"], user)
    else:
        user = st.session_state.user
    
    # Process recommendation when needed
    if "recommendation_shown" not in st.session_state or not st.session_state.recommendation_shown:
        with st.spinner("Finding the perfect activity for you..."):
            try:
                # Get the activity graph instance
                activity_graph = st.session_state.activity_graph
                
                # Setup initial state for LangGraph
                initial_state = {
                    "user": user,
                    "user_feedback": st.session_state.get("user_feedback"),
                    "errors": []
                }
                
                # Execute the graph to get a recommendation
                final_state = activity_graph.run(initial_state)
                
                # Store the result in session state
                st.session_state.recommendation_data = final_state["recommendation"]
                st.session_state.errors = final_state.get("errors", [])
                
                # Reset user feedback after using it
                if st.session_state.get("user_feedback"):
                    st.session_state.previous_feedback = st.session_state.user_feedback
                    st.session_state.user_feedback = None
                
                st.session_state.recommendation_shown = True
                
            except Exception as e:
                logger.error(f"Unexpected error in recommendation process: {str(e)}")
                logger.error(traceback.format_exc())
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
        
        # Display image if available
        if data.get("image_url"):
            st.image(data["image_url"], use_container_width=True)
            
            # Show user context below the image
            st.markdown("""
            <div style="background-color: #f0f2f6; padding: 16px; border-radius: 12px; margin-top: 20px;">
              <h4 style="margin-top: 0;">🌤️ Your Current Context</h4>
              <ul style="padding-left: 1em; list-style: none;">
                <li><strong>Weather:</strong> {weather}</li>
                <li><strong>Current Time:</strong> {current_time}</li>
                <li><strong>Free Hours Available:</strong> {free_hours} hours</li>
              </ul>
              <h5 style="margin-bottom: 0.5em;">📅 Today's Events:</h5>
              <ul style="padding-left: 1em; list-style: disc;">
                {calendar_items}
              </ul>
            </div>
            """.format(
                weather=user.get("weather", "Unknown"),
                current_time=user.get("current_time", "Unknown"),
                free_hours=user.get("free_hours", "Unknown"),
                calendar_items="\n".join(
                    f"<li><strong>{event['event']}</strong> from {event['start']} to {event['end']}</li>"
                    for event in user.get("calendar", [])
                )
            ), unsafe_allow_html=True)
        
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
                # Get storage manager to update preferences
                storage_manager = st.session_state.chroma_manager
                
                # Prepare feedback data
                feedback_data = {
                    "user_id": user["user_id"],
                    "activity_id": data.get("id", "unknown"),
                    "activity_type": data.get("type", "unknown"),
                    "activity_name": data.get("name", "Unknown"),
                    "interest_category": data.get("activity_type", "unknown"),
                    "feedback_type": "like",
                    "timestamp": datetime.now().isoformat()
                }
                
                # Add feedback to storage
                storage_manager.add_feedback(feedback_data)
                
                st.balloons()
                st.success("Great! I'll remember you liked this for future recommendations!")
        
        with col2:
            if st.button("👎 Show me something else"):
                # Get storage manager to update preferences
                storage_manager = st.session_state.chroma_manager
                
                # Prepare feedback data
                feedback_data = {
                    "user_id": user["user_id"],
                    "activity_id": data.get("id", "unknown"),
                    "activity_type": data.get("type", "unknown"),
                    "activity_name": data.get("name", "Unknown"),
                    "interest_category": data.get("activity_type", "unknown"),
                    "feedback_type": "dislike",
                    "timestamp": datetime.now().isoformat()
                }
                
                # Add feedback to storage
                storage_manager.add_feedback(feedback_data)
                
                # Store feedback to use in next recommendation
                st.session_state.user_feedback = "The user did not like the previous suggestion. Please provide a completely different recommendation."
                
                # Reset recommendation to get new one
                st.session_state.recommendation_shown = False
                st.rerun()
        
        # Tell me more button
        if st.button("🔎 Tell me more"):
            # Get storage manager to update preferences
            storage_manager = st.session_state.chroma_manager
            
            # Prepare feedback data for view details action
            feedback_data = {
                "user_id": user["user_id"],
                "activity_id": data.get("id", "unknown"),
                "activity_type": data.get("type", "unknown"),
                "activity_name": data.get("name", "Unknown"),
                "interest_category": data.get("activity_type", "unknown"),
                "feedback_type": "view_details",
                "timestamp": datetime.now().isoformat()
            }
            
            # Add feedback to storage
            storage_manager.add_feedback(feedback_data)
            
            # Get activity graph to generate details
            activity_graph = st.session_state.activity_graph
            
            # Call detail expansion node
            detail_state = {
                "user": user,
                "recommendation": data,
                "errors": []
            }
            
            expanded_state = activity_graph.expand_details(detail_state)
            
            # Display the detailed information
            st.markdown(f"### 📖 More details:\n\n{expanded_state.get('detailed_description', 'No details available')}")
            
            # Display maps link if available
            if expanded_state.get("maps_html"):
                st.markdown(expanded_state["maps_html"], unsafe_allow_html=True)
    
    # Display errors if any occurred
    if "errors" in st.session_state and st.session_state.errors:
        with st.expander("Troubleshooting Information", expanded=False):
            st.warning("Some issues occurred while generating your recommendations. We've provided alternatives instead.")
            for error in st.session_state.errors[-3:]:  # Show only the most recent errors
                st.error(error)
            if st.button("Clear Errors"):
                st.session_state.errors = []
                st.rerun()

# Tab 2: Admin Dashboard
with tabs[1]:
    st.header("Storage Admin Dashboard")
    
    # Simple authentication
    admin_password = st.text_input("Enter admin password", type="password")
    
    if admin_password == st.secrets.get("ADMIN_PASSWORD", "admin"):  # Use a real password in production
        # Get the storage manager
        storage_manager = st.session_state.chroma_manager
        
        # Create tabs for different data views
        admin_tabs = st.tabs(["Users", "Activities", "Feedback", "Statistics"])
        
        # Tab 1: Users Collection
        with admin_tabs[0]:
            st.subheader("User Profiles")
            
            # Get all users
            users = storage_manager.get_all_users()
            
            if users:
                user_ids = [u['user_id'] for u in users]
                selected_user_id = st.selectbox("Select User", user_ids)
                
                # Show selected user details
                selected_user = next((u for u in users if u['user_id'] == selected_user_id), None)
                if selected_user:
                    st.json(selected_user)
                    
                    # Option to delete user
                    if st.button("Delete User"):
                        storage_manager.delete_user(selected_user_id)
                        st.success(f"User {selected_user_id} deleted")
                        st.rerun()
            else:
                st.info("No users found in the database")
        
        # Tab 2: Activities Collection
        with admin_tabs[1]:
            st.subheader("Activity History")
            
            # Get all activities
            activities = storage_manager.get_all_activities()
            
            if activities:
                # Group by type
                indoor_activities = [a for a in activities if a.get('type') == 'indoor']
                outdoor_activities = [a for a in activities if a.get('type') == 'outdoor']
                
                st.write(f"Total Activities: {len(activities)} (Indoor: {len(indoor_activities)}, Outdoor: {len(outdoor_activities)})")
                
                activity_type = st.radio("Filter by Type", ["All", "Indoor", "Outdoor"])
                
                filtered_activities = activities
                if activity_type == "Indoor":
                    filtered_activities = indoor_activities
                elif activity_type == "Outdoor":
                    filtered_activities = outdoor_activities
                
                # Display activities
                for activity in filtered_activities[:10]:  # Limit to 10 to avoid cluttering the UI
                    with st.expander(f"{activity.get('name')} ({activity.get('id')})"):
                        st.json(activity)
            else:
                st.info("No activities found in the database")
        
        # Tab 3: Feedback Collection
        with admin_tabs[2]:
            st.subheader("User Feedback")
            
            # Get all feedback
            feedback = storage_manager.get_all_feedback()
            
            if feedback:
                # Group by type
                likes = [f for f in feedback if f.get('feedback_type') == 'like']
                dislikes = [f for f in feedback if f.get('feedback_type') == 'dislike']
                views = [f for f in feedback if f.get('feedback_type') == 'view_details']
                
                st.write(f"Total Feedback: {len(feedback)} (Likes: {len(likes)}, Dislikes: {len(dislikes)}, Views: {len(views)})")
                
                feedback_type = st.radio("Filter by Feedback Type", ["All", "Likes", "Dislikes", "Views"])
                
                filtered_feedback = feedback
                if feedback_type == "Likes":
                    filtered_feedback = likes
                elif feedback_type == "Dislikes":
                    filtered_feedback = dislikes
                elif feedback_type == "Views":
                    filtered_feedback = views
                
                # Display feedback
                for fb in filtered_feedback[:10]:  # Limit to 10 to avoid cluttering the UI
                    with st.expander(f"{fb.get('activity_name')} - {fb.get('feedback_type')}"):
                        st.json(fb)
            else:
                st.info("No feedback found in the database")
        
        # Tab 4: Statistics
        with admin_tabs[3]:
            st.subheader("User Statistics")
            
            # Get statistics
            stats = storage_manager.get_statistics()
            
            # Display user preference stats
            st.write("### Interest Categories Popularity")
            if stats.get("category_counts"):
                # Create a bar chart
                category_data = stats["category_counts"]
                st.bar_chart(category_data)
            else:
                st.info("No category data available")
            
            # Display activity type stats
            st.write("### Activity Type Distribution")
            if stats.get("activity_type_counts"):
                # Create a pie chart (Streamlit doesn't have native pie charts, so we'll use text)
                type_data = stats["activity_type_counts"]
                for activity_type, count in type_data.items():
                    st.write(f"- {activity_type}: {count}")
            else:
                st.info("No activity type data available")
            
            # Option to export data
            st.write("### Export Data")
            export_type = st.selectbox("Select data to export", ["Users", "Activities", "Feedback"])
            
            if st.button("Export as JSON"):
                if export_type == "Users":
                    data = storage_manager.get_all_users()
                elif export_type == "Activities":
                    data = storage_manager.get_all_activities()
                else:  # Feedback
                    data = storage_manager.get_all_feedback()
                
                # Create JSON string
                json_data = json.dumps(data, indent=2)
                
                # Provide download link
                st.download_button(
                    label="Download JSON",
                    data=json_data,
                    file_name=f"{export_type.lower()}_export.json",
                    mime="application/json"
                )
    else:
        st.warning("Please enter the admin password to access this section")

# App footer
st.sidebar.markdown("---")
st.sidebar.caption("Activity Planner App • v2.0")

# Sidebar: User preferences summary
with st.sidebar:
    if "user" in st.session_state:
        user = st.session_state.user
        storage_manager = st.session_state.chroma_manager
        
        with st.expander("📊 Your Preference Profile"):
            # Get user preferences from storage
            user_preferences = storage_manager.get_user_preferences(user["user_id"])
            
            # Show category preferences
            st.subheader("Category Preferences")
            if user_preferences.get("category_preferences"):
                for category, score in sorted(user_preferences["category_preferences"].items(), key=lambda x: x[1], reverse=True):
                    st.write(f"- {category}: {score:.1f}")
            else:
                st.write("No preferences recorded yet.")
            
            # Show recent likes
            st.subheader("Recent Likes")
            recent_likes = storage_manager.get_recent_feedback(user["user_id"], "like", limit=3)
            if recent_likes:
                for item in recent_likes:
                    st.write(f"- {item['activity_name']} ({item['interest_category']})")
            else:
                st.write("No likes recorded yet.")
            
            # Show recent dislikes
            st.subheader("Recent Dislikes")
            recent_dislikes = storage_manager.get_recent_feedback(user["user_id"], "dislike", limit=3)
            if recent_dislikes:
                for item in recent_dislikes:
                    st.write(f"- {item['activity_name']} ({item['interest_category']})")
            else:
                st.write("No dislikes recorded yet.")
    
    # Reset buttons
    with st.expander("🔄 Reset Options"):
        col1, col2 = st.columns(2)
        
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
                # Keep only API keys and clients
                keep_keys = ["model", "ors_client", "gmaps_client", "chroma_manager", "activity_graph"]
                preserved_values = {k: v for k, v in st.session_state.items() if k in keep_keys}
                
                # Clear session state
                for key in list(st.session_state.keys()):
                    if key not in keep_keys:
                        del st.session_state[key]
                
                # Restore preserved values
                for k, v in preserved_values.items():
                    st.session_state[k] = v
                
                st.session_state.initialized = True
                st.rerun()
