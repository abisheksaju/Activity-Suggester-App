import os
import logging
import re
import random
import requests
from typing import List, Optional

from api_utils import safe_api_call, ImageError
import googlemaps

# Set up logging
logger = logging.getLogger('image_utils')

# Unsplash default key - replace with your own or use environment variable
UNSPLASH_ACCESS_KEY = os.environ.get("UNSPLASH_ACCESS_KEY", "rVvxvkYuJREpI8wMn9GvJUGhj5bZVlVFBkKMx1QquQA")

def extract_main_keywords(text: str) -> str:
    """
    Extract main keywords from activity description
    
    Args:
        text: Activity description text
        
    Returns:
        str: Main keyword extracted
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
            "dessert", "coffee", "tea", "smoothie", "cocktail", "pasta", "truffles"
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

def extract_keywords_from_prompt(prompt: str) -> List[str]:
    """
    Extract the most relevant keywords from an activity description for image search
    
    Args:
        prompt: Activity description
        
    Returns:
        List[str]: List of extracted keywords
    """
    try:
        # Fallback 1: Pattern-based extraction for specific activities
        # Look for bold or asterisk-emphasized text which often contains the activity name
        emphasized = re.findall(r'\*\*(.*?)\*\*|\*(.*?)\*', prompt)
        emphasized_keywords = []
        for match_pair in emphasized:
            # Each match is a tuple with one empty value
            for match in match_pair:
                if match:
                    emphasized_keywords.append(match)
        
        if emphasized_keywords:
            return emphasized_keywords + extract_food_keywords(prompt)
        
        # Fallback 2: Look for food/activity specific patterns
        food_keywords = extract_food_keywords(prompt)
        if food_keywords:
            return food_keywords
            
        # Fallback 3: Extract phrases that might be activities
        activity_phrases = re.findall(r'(making|cooking|baking|playing|watching|trying) ([a-zA-Z\s]+)', prompt)
        if activity_phrases:
            return [f"{verb} {obj}" for verb, obj in activity_phrases[:2]] + extract_nouns(prompt)[:1]
        
        # Final fallback: Just extract potential nouns
        return extract_nouns(prompt)
        
    except Exception as e:
        logger.error(f"All keyword extraction methods failed: {str(e)}")
        # Last resort - split by spaces and take longest words (likely nouns)
        words = prompt.split()
        words.sort(key=len, reverse=True)
        return words[:3] if words else ["activity"]

def extract_food_keywords(text: str) -> List[str]:
    """
    Extract food-related keywords which are common in indoor activities
    
    Args:
        text: Activity description
        
    Returns:
        List[str]: List of food-related keywords
    """
    # Common food patterns
    food_patterns = [
        r"(?:making|cooking|baking|prepare|preparing|homemade) ([a-zA-Z\s]+)",  # cooking X
        r"(?:make|cook|bake|try) ([a-zA-Z\s]+)",  # make X
        r"([a-zA-Z\s]+) recipe",  # X recipe
        r"([a-zA-Z\s]+) from scratch"  # X from scratch
    ]
    
    matches = []
    for pattern in food_patterns:
        found = re.findall(pattern, text.lower())
        if found:
            matches.extend(found)
    
    # Clean up matches
    cleaned = []
    for match in matches:
        # Remove articles and filler words
        for word in ["a", "the", "some", "your", "own"]:
            match = re.sub(r'\b' + word + r'\b', '', match)
        match = re.sub(r'\s+', ' ', match).strip()
        if match and len(match) > 3:
            cleaned.append(match)
    
    return cleaned[:3] if cleaned else []

def extract_nouns(text: str) -> List[str]:
    """
    Extract potential nouns from text
    
    Args:
        text: Activity description
        
    Returns:
        List[str]: List of potential nouns
    """
    # Simple regex-based noun extraction
    # Words that are capitalized or 4+ characters and not in stop list
    stop_words = ["that", "this", "with", "from", "your", "have", "will", "what", 
                 "about", "which", "when", "make", "like", "how", "can", "time",
                 "just", "being", "some", "take", "into", "spicy", "delicious", "easy"]
    
    # First look for noun phrases
    noun_phrases = re.findall(r'([a-zA-Z]{3,}(?:\s+[a-zA-Z]{3,}){1,2})', text)
    
    # Then individual potential nouns
    words = re.findall(r'\b[A-Za-z]{4,}\b', text)
    
    # Filter and combine
    result = []
    
    for phrase in noun_phrases:
        if all(word.lower() not in stop_words for word in phrase.split()):
            result.append(phrase)
    
    for word in words:
        if word.lower() not in stop_words:
            result.append(word)
    
    # Deduplicate and limit
    unique_results = []
    for item in result:
        if item not in unique_results:
            unique_results.append(item)
    
    return unique_results[:3]

def simplify_keyword(keyword: str) -> str:
    """
    Simplify a complex keyword phrase to increase hit rate with image APIs
    
    Args:
        keyword: Original keyword
        
    Returns:
        str: Simplified keyword
    """
    # If keyword is already simple, return as is
    if len(keyword.split()) <= 2:
        return keyword
        
    # Remove common phrases that make keywords too specific
    removable_phrases = [
        "from scratch", "homemade", "a batch of", "watching", "making", "cooking",
        "baking", "playing", "trying", "batch of", "going to", "session of"
    ]
    
    result = keyword.lower()
    for phrase in removable_phrases:
        result = result.replace(phrase, "")
    
    # Clean up extra spaces
    result = re.sub(r'\s+', ' ', result).strip()
    
    return result

def extract_core_keyword(keyword: str) -> str:
    """
    Extract the core subject from a keyword phrase
    Example: "batch of homemade pasta from scratch" -> "pasta"
    
    Args:
        keyword: Original keyword
        
    Returns:
        str: Core keyword
    """
    # List of common subjects
    common_subjects = [
        "pasta", "pizza", "movie", "film", "game", "book", "yoga", "meditation",
        "painting", "drawing", "music", "coffee", "tea", "cake", "cookie", "bread",
        "soup", "salad", "dessert", "craft", "puzzle", "chess", "board game"
    ]
    
    # First check if any common subject is in the keyword
    keyword_lower = keyword.lower()
    for subject in common_subjects:
        if subject in keyword_lower:
            return subject
    
    # If not found, just take the last word (often the main subject)
    words = keyword_lower.split()
    if words:
        # Remove common modifiers if they're the last word
        if words[-1] in ["recipe", "activity", "project", "session"]:
            if len(words) > 1:
                return words[-2]
        return words[-1]
    
    return keyword  # Fallback to original

@safe_api_call
def fetch_unsplash_image(keyword: str) -> Optional[str]:
    """
    Fetch an image from Unsplash API for a given keyword with improved reliability
    
    Args:
        keyword: Keyword to search for
        
    Returns:
        str or None: Image URL or None if not found
    """
    try:
        # Check if we have an Unsplash API key in the environment
        access_key = os.environ.get("UNSPLASH_ACCESS_KEY", UNSPLASH_ACCESS_KEY)
        
        # Simplify the keyword to improve hit rate
        original_keyword = keyword
        simplified_keyword = simplify_keyword(keyword)
        core_keyword = extract_core_keyword(keyword)
        
        # List of keywords to try, in order of specificity
        keywords_to_try = [
            simplified_keyword,
            core_keyword,
            # Add some category-specific generic terms
            f"{core_keyword} activity",
            original_keyword
        ]
        
        # Remove duplicates while preserving order
        unique_keywords = []
        for kw in keywords_to_try:
            if kw and kw not in unique_keywords:
                unique_keywords.append(kw)
        
        # Log the keywords we'll try
        logger.info(f"Trying Unsplash with keywords: {unique_keywords}")
        
        # Try each keyword with the API method first
        if access_key:
            for kw in unique_keywords:
                try:
                    response = requests.get(
                        "https://api.unsplash.com/search/photos",
                        params={
                            "query": kw,
                            "client_id": access_key,
                            "per_page": 3
                        }
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        if data["results"] and len(data["results"]) > 0:
                            # Return the regular sized image URL
                            image_url = data["results"][0]["urls"]["regular"]
                            logger.info(f"Found Unsplash image with API for '{kw}'")
                            return image_url
                except Exception as api_err:
                    logger.warning(f"API method failed for '{kw}': {api_err}")
                    continue
        
        # Fall back to the direct URL method which is more reliable
        for kw in unique_keywords:
            try:
                sanitized_keyword = kw.replace(" ", "+")
                direct_url = f"https://source.unsplash.com/1600x900/?{sanitized_keyword}"
                
                # Check if URL returns a valid image
                response = requests.head(direct_url, allow_redirects=True)
                if response.status_code == 200:
                    logger.info(f"Found Unsplash image with direct URL for '{kw}'")
                    return direct_url
            except Exception as direct_err:
                logger.warning(f"Direct URL method failed for '{kw}': {direct_err}")
                continue
        
        # Final fallback to a very generic term
        return "https://source.unsplash.com/1600x900/?activity"
            
    except Exception as e:
        logger.error(f"All Unsplash methods failed for '{keyword}': {str(e)}")
        # Ultimate fallback
        return "https://source.unsplash.com/1600x900/?activity"

@safe_api_call
def fetch_google_images(keyword: str, GOOGLE_CSE_ID: str, GOOGLE_API_KEY: str) -> Optional[str]:
    """
    Fetch images using Google Custom Search API as a more robust alternative
    
    Args:
        keyword: Keyword to search for
        GOOGLE_CSE_ID: Google Custom Search Engine ID
        GOOGLE_API_KEY: Google API key
        
    Returns:
        str or None: Image URL or None if not found
    """
    if not GOOGLE_CSE_ID or not GOOGLE_API_KEY:
        logger.warning("Missing Google CSE credentials")
        return None
        
    # Simplify the keyword to improve hit rate
    simplified_keyword = simplify_keyword(keyword)
        
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        'q': simplified_keyword,
        'cx': GOOGLE_CSE_ID,
        'key': GOOGLE_API_KEY,
        'searchType': 'image',
        'num': 1
    }
    
    response = requests.get(url, params=params)
    
    if response.status_code == 200:
        data = response.json()
        if 'items' in data and len(data['items']) > 0:
            return data['items'][0]['link']
    else:
        logger.warning(f"Google CSE error: {response.status_code}")
        
    return None

@safe_api_call
def fetch_image_for_keyword(keyword: str, GOOGLE_MAPS_API_KEY: str, GOOGLE_CSE_ID: str = None, GOOGLE_CSE_API_KEY: str = None) -> Optional[str]:
    """
    Fetch an image for a specific keyword using multiple services with improved fallbacks
    
    Args:
        keyword: Keyword to search for
        GOOGLE_MAPS_API_KEY: Google Maps API key
        GOOGLE_CSE_ID: Optional Google Custom Search Engine ID
        GOOGLE_CSE_API_KEY: Optional Google Custom Search API key
        
    Returns:
        str or None: Image URL or None if not found
    """
    if not keyword:
        return None
    
    logger.info(f"Fetching image for keyword: {keyword}")
    original_keyword = keyword
    simplified_keyword = simplify_keyword(keyword)
    core_keyword = extract_core_keyword(keyword)
    
    logger.info(f"Original: '{original_keyword}', Simplified: '{simplified_keyword}', Core: '{core_keyword}'")

    # Try Unsplash first for indoor activities
    logger.info(f"Trying Unsplash with original keyword: {original_keyword}")
    unsplash_url = fetch_unsplash_image(original_keyword)
    if unsplash_url:
        logger.info("Got image from Unsplash with original keyword")
        return unsplash_url
        
    # Try simplified keyword
    logger.info(f"Trying Unsplash with simplified keyword: {simplified_keyword}")
    unsplash_url = fetch_unsplash_image(simplified_keyword)
    if unsplash_url:
        logger.info("Got image from Unsplash with simplified keyword")
        return unsplash_url
        
    # Try core keyword
    logger.info(f"Trying Unsplash with core keyword: {core_keyword}")
    unsplash_url = fetch_unsplash_image(core_keyword)
    if unsplash_url:
        logger.info("Got image from Unsplash with core keyword")
        return unsplash_url

    # Only if Unsplash fails, try Google Maps API
    try:
        gmaps = googlemaps.Client(key=GOOGLE_MAPS_API_KEY)

        # Search for places related to the keyword
        places_result = gmaps.places(
            query=simplified_keyword,
            language="en",
        )

        places_with_photos = [place for place in places_result.get("results", [])
                          if place.get("photos")]

        if places_with_photos:
            # Select a random place with photos
            selected_place = random.choice(places_with_photos)

            # Get the photo reference
            photo_reference = selected_place["photos"][0]["photo_reference"]

            # Build the URL for the photo
            image_url = f"https://maps.googleapis.com/maps/api/place/photo?maxwidth=400&photoreference={photo_reference}&key={GOOGLE_MAPS_API_KEY}"
            
            logger.info("Got image from Google Places API")
            return image_url
    except Exception as e:
        logger.warning(f"Google Places image fetch failed: {str(e)}")
    
    # Try Google Custom Search API if available
    if GOOGLE_CSE_ID and GOOGLE_CSE_API_KEY:
        try:
            google_image = fetch_google_images(original_keyword, GOOGLE_CSE_ID, GOOGLE_CSE_API_KEY)
            if google_image:
                logger.info("Got image from Google Custom Search API")
                return google_image
                
            # Try with simplified keyword
            google_image = fetch_google_images(simplified_keyword, GOOGLE_CSE_ID, GOOGLE_CSE_API_KEY)
            if google_image:
                logger.info("Got image from Google Custom Search API with simplified keyword")
                return google_image
                
            # Try with core keyword
            google_image = fetch_google_images(core_keyword, GOOGLE_CSE_ID, GOOGLE_CSE_API_KEY)
            if google_image:
                logger.info("Got image from Google Custom Search API with core keyword")
                return google_image
        except Exception as e:
            logger.warning(f"Google CSE image fetch failed: {str(e)}")
        
    return None

@safe_api_call
def fetch_place_image(place: dict, api_key: str) -> Optional[str]:
    """
    Fetch an image for a place using Google Places API
    
    Args:
        place: Place data from Google Maps API
        api_key: Google Maps API key
        
    Returns:
        str or None: Image URL or None if not found
    """
    if not place or 'photos' not in place or not place['photos']:
        return None
    
    # Get the photo reference
    photo_reference = place['photos'][0]['photo_reference']
    
    # Build the URL for the photo
    image_url = f"https://maps.googleapis.com/maps/api/place/photo?maxwidth=400&photoreference={photo_reference}&key={api_key}"
    
    return image_url

def fetch_image_for_activity(activity_data: dict, google_maps_api_key: str) -> Optional[str]:
    """
    Fetch an appropriate image for an activity
    
    Args:
        activity_data: Activity data
        google_maps_api_key: Google Maps API key
        
    Returns:
        str or None: Image URL or None if not found
    """
    # If activity already has an image, return it
    if activity_data.get("image_url"):
        return activity_data["image_url"]
    
    # For outdoor activities, try to get place image
    if activity_data.get("type") == "outdoor" and activity_data.get("place"):
        place_image = fetch_place_image(activity_data["place"], google_maps_api_key)
        if place_image:
            return place_image
    
    # For indoor activities or if place image fails, try keyword-based approach
    activity_type = activity_data.get("activity_type", "activity")
    description = activity_data.get("description", "")
    
    # Try to extract keywords from description
    keywords = extract_keywords_from_prompt(description)
    
    # Try each keyword
    for keyword in keywords:
        if keyword and len(keyword) >= 3:
            image_url = fetch_image_for_keyword(keyword, google_maps_api_key)
            if image_url:
                return image_url
    
    # Fall back to activity type
    return fetch_unsplash_image(activity_type)
