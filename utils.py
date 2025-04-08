# Add these imports at the top of utils.py
import traceback
import logging
from PIL import UnidentifiedImageError
import random
import re

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('activity_suggester')

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
            "dessert", "coffee", "tea", "smoothie", "cocktail"
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

# Enhanced indoor activity function with image
def build_llm_prompt_indoor(user_context, top_interest, user_feedback=None):
    """Build prompt for indoor activity with better error handling"""
    try:
        feedback_note = "" if not user_feedback else f"{user_feedback} "

        # Add personalized context
        personalized_context = build_personalized_context(user_context, top_interest)

        prompt = f"""
{feedback_note}You are a personalized indoor activity planner.
User's top interest is: {top_interest}
Current weather: {user_context['weather']}
Time: {user_context['current_time']}
Free time available: {user_context['free_hours']} hours
Location: {user_context['location']['city']}

User History and Preferences:
{personalized_context}

Suggest a single interesting indoor activity that suits the user's interest and context. Make it personal, fun, and specific to {top_interest}. Make the output 1–2 short, fun, personal sentences that could show up on a phone lockscreen.
"""
        return prompt
    except Exception as e:
        logger.error(f"Error building indoor prompt: {str(e)}")
        # Provide a simplified fallback prompt
        return f"Suggest a fun indoor {top_interest} activity in 1-2 sentences."

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