import os
import json
import uuid
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional, Union
from collections import Counter

class JSONStorageManager:
    """
    A replacement for ChromaManager that uses simple JSON files for storage.
    This is more compatible with Streamlit Cloud.
    """
    
    def __init__(self, storage_directory: str = ".storage"):
        """Initialize storage directories"""
        self.logger = logging.getLogger('json_storage_manager')
        
        # Create storage directory if it doesn't exist
        self.storage_directory = storage_directory
        os.makedirs(storage_directory, exist_ok=True)
        
        # Create subdirectories for each collection
        self.users_dir = os.path.join(storage_directory, "users")
        self.activities_dir = os.path.join(storage_directory, "activities")
        self.places_dir = os.path.join(storage_directory, "places")
        self.feedback_dir = os.path.join(storage_directory, "feedback")
        
        os.makedirs(self.users_dir, exist_ok=True)
        os.makedirs(self.activities_dir, exist_ok=True)
        os.makedirs(self.places_dir, exist_ok=True)
        os.makedirs(self.feedback_dir, exist_ok=True)
        
        self.logger.info("Storage directories initialized")
    
    def _save_json(self, directory: str, file_id: str, data: Dict) -> bool:
        """Helper method to save JSON to a file"""
        try:
            file_path = os.path.join(directory, f"{file_id}.json")
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)
            return True
        except Exception as e:
            self.logger.error(f"Error saving JSON: {str(
