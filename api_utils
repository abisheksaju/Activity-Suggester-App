import logging
import traceback
import functools
from typing import Callable, Any, Tuple

import openrouteservice
import googlemaps

# Custom exception classes
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

# Set up logging
logger = logging.getLogger('api_utils')

def safe_api_call(func):
    """Decorator for safely calling API functions"""
    @functools.wraps(func)
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

# Set up clients
def init_clients(openroute_api_key, google_maps_api_key) -> Tuple[Any, Any]:
    """
    Initialize API clients for OpenRouteService and Google Maps
    
    Args:
        openroute_api_key: OpenRouteService API key
        google_maps_api_key: Google Maps API key
        
    Returns:
        Tuple containing (ors_client, gmaps_client)
    """
    try:
        ors_client = openrouteservice.Client(key=openroute_api_key)
        gmaps_client = googlemaps.Client(key=google_maps_api_key)
        return ors_client, gmaps_client
    except Exception as e:
        logger.error(f"Error initializing clients: {str(e)}")
        raise APIError(f"Error initializing API clients: {str(e)}", "client_init", e)

@safe_api_call
def get_route_duration(origin, destination, ors_client):
    """
    Get the route duration between two points using OpenRouteService
    Returns time in minutes
    """
    # Make sure coordinates are valid
    if not all(origin) or not all(destination):
        return None
    
    # Request route from ORS API
    route = ors_client.directions(
        coordinates=[origin, destination],
        profile='driving-car',
        format='geojson'
    )
    
    # Extract duration in seconds and convert to minutes
    if route and 'features' in route and len(route['features']) > 0:
        duration_seconds = route['features'][0]['properties']['summary']['duration']
        return round(duration_seconds / 60)  # Convert to minutes
    
    return None
