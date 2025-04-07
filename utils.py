import datetime
import random

def get_free_hours(user_calendar):
    """
    Dummy function that returns free hours from user calendar.
    """
    return random.choice([1, 2, 3])

def get_top_interest(user_context):
    """
    Dummy function to extract top interest.
    """
    return user_context.get("interests", ["cafe"])[0]

def format_user_context(raw_context):
    """
    Converts raw context (like location string) into a structured format.
    """
    city, coords = raw_context["location"].split(" (")
    lat, lon = map(float, coords.strip(")").split(", "))
    return {
        "city": city,
        "lat": lat,
        "lon": lon,
        "weather": raw_context["weather"],
        "current_time": raw_context["current_time"],
        "free_hours": raw_context["free_hours"],
        "interests": raw_context["interests"]
    }
