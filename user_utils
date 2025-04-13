import logging
import uuid
from typing import Dict, Any, List, Optional
import random
from datetime import datetime

# Set up logging
logger = logging.getLogger('user_utils')

def get_synthetic_user() -> Dict[str, Any]:
    """
    Generate synthetic user data with automatically calculated free hours
    based on calendar and current time.
    
    Returns:
        Dict: Synthetic user data
    """
    # Generate a unique user ID
    user_id = str(uuid.uuid4())
    
    # Define the user's base information
    user_data = {
        "user_id": user_id,
        "location": {
            "city": "Bangalore",
            "lat": 12.9716,
            "lon": 77.5946
        },
        "weather": random.choice(["Sunny", "Cloudy", "Rainy", "Clear", "Hot"]),
        "current_time": f"{random.choice(['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'])} {random.randint(6, 10)} AM",
        "calendar": [
            {"event": "Lunch with friend", "start": "1 PM", "end": "2 PM"},
            {"event": "Office Meeting", "start": "6 PM", "end": "7 PM"}
        ],
        "interests": {
            "travel": round(random.uniform(0.6, 0.9), 2),
            "food": round(random.uniform(0.5, 0.8), 2),
            "news": round(random.uniform(0.3, 0.7), 2),
            "shopping": round(random.uniform(0.4, 0.7), 2),
            "gaming": round(random.uniform(0.5, 0.8), 2),
            "fitness": round(random.uniform(0.6, 0.9), 2),
            "cooking": round(random.uniform(0.5, 0.8), 2)
        },
        "created_at": datetime.now().isoformat()
    }
    
    # Calculate free hours based on current time and calendar
    user_data["free_hours"] = calculate_free_time(
        user_data["current_time"], 
        user_data["calendar"]
    )
    
    return user_data

def calculate_free_time(current_time_str: str, calendar_events: List[Dict[str, str]], max_hours: int = 6) -> int:
    """
    Calculate free time until next calendar event, with a maximum limit.
    
    Args:
        current_time_str: String representing current time (e.g., "Friday 2:30 PM")
        calendar_events: List of calendar events with start and end times
        max_hours: Maximum number of free hours to return (default: 6)
        
    Returns:
        int: Number of free hours until next event, capped at max_hours
    """
    try:
        # Parse the current time string
        day_parts = current_time_str.split()
        
        # Handle different time formats: "Friday 2:30 PM" or "Friday 2 PM"
        time_str = " ".join(day_parts[1:])  # Extract the time portion
        
        # Parse hour and minute
        current_hour = 0
        current_minute = 0
        
        if ":" in time_str:
            # Format like "2:30 PM"
            time_parts = time_str.split(":")
            current_hour = int(time_parts[0])
            
            # Extract minutes from the second part which may contain AM/PM
            minute_part = time_parts[1].split()[0]
            current_minute = int(minute_part)
            
            # Check for AM/PM
            if "PM" in time_str.upper() and current_hour < 12:
                current_hour += 12
            elif "AM" in time_str.upper() and current_hour == 12:
                current_hour = 0
        else:
            # Format like "2 PM"
            hour_part = time_str.split()[0]
            current_hour = int(hour_part)
            
            # Check for AM/PM
            if "PM" in time_str.upper() and current_hour < 12:
                current_hour += 12
            elif "AM" in time_str.upper() and current_hour == 12:
                current_hour = 0
        
        # Current time in minutes since midnight
        current_time_minutes = current_hour * 60 + current_minute
        
        # Track ongoing events and find next event
        is_in_event = False
        next_event_minutes = None
        
        for event in calendar_events:
            event_start = event.get("start", "")
            event_end = event.get("end", "")
            
            if not event_start:
                continue
                
            # Parse event start time
            start_minutes = parse_time_to_minutes(event_start)
            
            # Parse event end time if available
            end_minutes = 23 * 60 + 59  # Default to end of day
            if event_end:
                end_minutes = parse_time_to_minutes(event_end)
            
            # Check if user is currently in an event
            # This means the user is considered free exactly at the end time of an event
            if start_minutes <= current_time_minutes < end_minutes:
                is_in_event = True
                break
            
            # If not in an event, check if this is the next upcoming event
            elif start_minutes > current_time_minutes:
                if next_event_minutes is None or start_minutes < next_event_minutes:
                    next_event_minutes = start_minutes
        
        # Calculate free hours
        if is_in_event:
            # User is currently in an event - no free time now
            return 0
        elif next_event_minutes is None:
            # No future events today
            return max_hours
        else:
            free_minutes = next_event_minutes - current_time_minutes
            free_hours = free_minutes / 60.0
            return min(max(round(free_hours), 0), max_hours)
            
    except Exception as e:
        # If anything goes wrong, log and return a default value
        logger.error(f"Error calculating free time: {str(e)}")
        return 3  # Default value

def parse_time_to_minutes(time_str: str) -> int:
    """
    Helper function to parse time strings to minutes since midnight
    
    Args:
        time_str: Time string in format like "1:30 PM" or "1 PM"
        
    Returns:
        int: Minutes since midnight
    """
    try:
        hour, minute = 0, 0
        
        if ":" in time_str:
            # Format like "1:30 PM"
            time_parts = time_str.split(":")
            hour = int(time_parts[0])
            
            # Extract minutes from the second part which may contain AM/PM
            minute_part = time_parts[1].split()[0]
            minute = int(minute_part)
            
            # Check for AM/PM
            if "PM" in time_str.upper() and hour < 12:
                hour += 12
            elif "AM" in time_str.upper() and hour == 12:
                hour = 0
        else:
            # Format like "1 PM"
            hour_part = time_str.split()[0]
            hour = int(hour_part)
            
            # Check for AM/PM
            if "PM" in time_str.upper() and hour < 12:
                hour += 12
            elif "AM" in time_str.upper() and hour == 12:
                hour = 0
                
        return hour * 60 + minute
    except Exception:
        return 0  # Default in case of error
