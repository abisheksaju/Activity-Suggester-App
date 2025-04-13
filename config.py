"""
Configuration settings for the Activity Suggester app
"""
import os

# App settings
SETTINGS = {
    # ChromaDB settings
    "chroma_db": {
        "persist_directory": ".chromadb",
        "chroma_db_impl": "duckdb+parquet", 
    },
    
    # LangGraph settings
    "langgraph": {
        "debug": True,
    },
    
    # Default user preferences
    "default_preferences": {
        "category_preferences": {
            "food": 0.8,
            "travel": 0.6,
            "shopping": 0.5,
            "gaming": 0.5,
            "news": 0.4,
            "fitness": 0.7,
            "cooking": 0.7
        }
    },
    
    # Image settings
    "image": {
        "unsplash_access_key": os.environ.get("UNSPLASH_ACCESS_KEY", "rVvxvkYuJREpI8wMn9GvJUGhj5bZVlVFBkKMx1QquQA"),
        "use_google_cse": False,
    },
    
    # Streamlit settings
    "streamlit": {
        "page_title": "Activity Suggester",
        "layout": "centered",
        "admin_password": os.environ.get("ADMIN_PASSWORD", "admin"),
    }
}
