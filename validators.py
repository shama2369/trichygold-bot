"""
Validation utilities for TrichyGold Bot
"""
import re
import logging

logger = logging.getLogger(__name__)

def is_valid_chat_id(chat_id):
    """
    Validates if a chat ID is in the correct format for Telegram.
    
    Telegram chat IDs are typically numeric strings.
    User IDs are positive integers.
    Group chat IDs are negative integers.
    Channel IDs start with -100 followed by numbers.
    
    Args:
        chat_id: The chat ID to validate (can be string or integer)
        
    Returns:
        bool: True if the chat ID is valid, False otherwise
    """
    if chat_id is None:
        return False
        
    # Convert to string if it's not already
    if not isinstance(chat_id, str):
        chat_id = str(chat_id)
    
    # Remove any leading/trailing whitespace
    chat_id = chat_id.strip()
    
    # Check if it's empty after stripping
    if not chat_id:
        return False
    
    # Check if it's a valid integer format
    if not re.match(r'^-?\d+$', chat_id):
        return False
    
    # Additional checks could be added here if needed
    # For example, length validation or specific format requirements
    
    return True

def validate_employee_data(name, chat_id):
    """
    Validates employee data before adding to the database.
    
    Args:
        name: Employee name
        chat_id: Employee chat ID
        
    Returns:
        tuple: (is_valid, error_message)
    """
    # Validate name
    if not name or not isinstance(name, str) or len(name.strip()) == 0:
        return False, "Employee name cannot be empty"
    
    if len(name) > 50:  # Reasonable limit for a name
        return False, "Employee name is too long (max 50 characters)"
    
    # Validate chat ID
    if not is_valid_chat_id(chat_id):
        return False, "Invalid chat ID format. Must be a valid Telegram ID."
    
    return True, None
