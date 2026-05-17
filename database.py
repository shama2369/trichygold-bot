import os
import re
import logging
import urllib.parse
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

import certifi
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError, OperationFailure

logger = logging.getLogger(__name__)


def get_mongodb_uri() -> Optional[str]:
    """Read MongoDB URI from env (MONGODB_URI preferred; MONGO_URI alias)."""
    uri = (
        os.getenv('MONGODB_URI')
        or os.getenv('MONGO_URI')
        or os.getenv('MONGO_URL')
    )
    if not uri:
        return None
    uri = uri.strip().strip('"').strip("'")
    if not uri.startswith(('mongodb://', 'mongodb+srv://')):
        logger.error(
            "Invalid MongoDB URI: must start with 'mongodb://' or 'mongodb+srv://'. "
            "Set MONGODB_URI on Railway to your full Atlas connection string."
        )
        return None
    return uri


def _encode_mongodb_uri(mongodb_uri: str) -> str:
    """URL-encode credentials in a MongoDB connection string."""
    if '@' not in mongodb_uri:
        return mongodb_uri
    try:
        prefix, rest = mongodb_uri.split('://', 1)
        auth_part, host_part = rest.split('@', 1)
        if ':' in auth_part:
            username, password = auth_part.split(':', 1)
            encoded_username = urllib.parse.quote_plus(username)
            encoded_password = urllib.parse.quote_plus(password)
            return f"{prefix}://{encoded_username}:{encoded_password}@{host_part}"
    except Exception as e:
        logger.warning(f"Failed to encode URI components: {e}")
    return mongodb_uri


class MongoDB:
    def __init__(self, uri=None):
        self.uri = uri or get_mongodb_uri()
        self.client = None
        self.db = None
        self.tasks = None
        self.employees = None
        self.inquiries = None
        self.notifications = None
        self.messages = None
        
        # Connection tracking variables
        self.connection_status = {
            "status": "disconnected",
            "last_attempt": None,
            "error": None,
            "server_info": None,
            "reconnect_attempts": 0
        }
        self.last_connection_attempt = None
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        self.reconnect_delay = 5  # seconds
        
        # Attempt initial connection
        self.connect()

    def _init_collections(self) -> None:
        """Bind collection handles after a successful connection."""
        if self.db is None:
            return
        self.tasks = self.db.tasks
        self.employees = self.db.employees
        self.inquiries = self.db.inquiries
        self.notifications = self.db.notifications
        self.messages = self.db.messages

    def ensure_ready(self) -> bool:
        """Ensure MongoDB is connected and collection handles exist."""
        if self.employees is not None and self.tasks is not None:
            try:
                self.db.command('ping')
                return True
            except Exception:
                pass
        if self.is_connected():
            self._init_collections()
            return self.employees is not None and self.tasks is not None
        if self.connect():
            return self.employees is not None and self.tasks is not None
        return False

    def connect(self):
        """Connect to MongoDB database"""
        try:
            # Get MongoDB URI from environment variables or constructor
            mongodb_uri = self.uri or get_mongodb_uri()
            self.uri = mongodb_uri
            
            if not mongodb_uri:
                logger.error("MONGODB_URI (or MONGO_URI) environment variable not set")
                self.connection_status["error"] = "MONGODB_URI (or MONGO_URI) environment variable not set"
                self.connection_status["status"] = "error"
                return False

            mongodb_uri = _encode_mongodb_uri(mongodb_uri)
            self.uri = mongodb_uri
                
            # Log URI components (without credentials) for debugging
            uri_parts = None
            try:
                uri_parts = re.match(r'mongodb(?:\+srv)?://(?:.*@)?([^/]+)(?:/([^?]+))?', mongodb_uri)
                if uri_parts:
                    logger.info("URI components have been properly URL-encoded")
            except Exception as e:
                logger.error(f"Error parsing URI: {e}")
                
            # Set connection timeout options (tlsCAFile required for Atlas on Railway)
            client_options = {
                'tlsCAFile': certifi.where(),
                'connectTimeoutMS': 30000,
                'socketTimeoutMS': 30000,
                'serverSelectionTimeoutMS': 30000,
                'retryWrites': True,
            }
            
            logger.info("Attempting to connect to MongoDB...")
            self.last_connection_attempt = datetime.now()
            
            # Initialize MongoDB client
            self.client = MongoClient(mongodb_uri, **client_options)
            logger.info("MongoDB client initialized")
            
            # Log connection details for debugging
            if uri_parts:
                logger.info(f"MongoDB URI pattern: {uri_parts.group(1)}")
            logger.info(f"MongoDB client options: {', '.join([f'{k}={v}' for k, v in client_options.items()])}")
            
            # Test connection with ping
            logger.info("Attempting to ping MongoDB server...")
            
            # Check if database name is in URI, if not use a default name
            db_name = None
            if uri_parts and uri_parts.group(2):
                db_name = uri_parts.group(2)
            else:
                # Use a default database name if none specified in URI
                db_name = 'trichygold'
                logger.info(f"No database specified in URI, using default: {db_name}")
                
            self.db = self.client[db_name]
            self.db.command('ping')
            
            # Get server info
            server_info = self.client.server_info()
            logger.info(f"Successfully connected to MongoDB. Server version: {server_info.get('version')}")
            
            self._init_collections()
            self._ensure_indexes()
            
            # Update connection status
            self.connection_status["status"] = "connected"
            self.connection_status["error"] = None
            self.connection_status["server_info"] = server_info
            self.connection_status["last_attempt"] = self.last_connection_attempt
            self.reconnect_attempts = 0
            
            logger.info("Using MongoDB for storage")
            return True
            
        except Exception as e:
            error_message = str(e)
            logger.error(f"Failed to connect to MongoDB: {error_message}")
            
            # Update connection status
            self.connection_status["status"] = "error"
            self.connection_status["error"] = error_message
            self.connection_status["last_attempt"] = self.last_connection_attempt
            
            return False

    def _ensure_indexes(self) -> None:
        """Create indexes after a successful connection."""
        if self.tasks is not None:
            try:
                self.tasks.create_index('task_id', unique=True)
            except Exception as e:
                logger.warning(f"Could not create tasks index: {e}")
        if self.inquiries is not None:
            try:
                self.inquiries.create_index('inquiry_id', unique=True)
            except Exception as e:
                logger.warning(f"Could not create inquiries index: {e}")

    def _connect_to_mongodb(self) -> bool:
        """Legacy alias used by try_reconnect."""
        return self.connect()
            
    # Task operations
    def create_task(self, task_id: int, task: str, employees: List[str], reminder_interval: int) -> Dict:
        """Create a new task in the database or in-memory storage"""
        task_doc = {
            'task_id': task_id,
            'task': task,
            'employees': employees,
            'status': 'active',
            'created_at': datetime.now(),
            'reminder_interval': reminder_interval,
            'inquiries': [],
            'clarifications': []
        }
        
        self.tasks.insert_one(task_doc)
        return task_doc
    
    def get_task(self, task_id: int) -> Optional[Dict]:
        """Get a task by its ID from database or in-memory storage"""
        return self.tasks.find_one({'task_id': task_id})
    
    def update_task_status(self, task_id: int, status: str, completed_by: str = None) -> bool:
        """Update a task's status in database or in-memory storage"""
        update = {
            '$set': {
                'status': status,
                'completed_at': datetime.now(),
                'completed_by': completed_by,
            }
        }
        result = self.tasks.update_one({'task_id': task_id}, update)
        return result.modified_count > 0
    
    def get_active_tasks(self) -> List[Dict]:
        """Get all active tasks from MongoDB"""
        try:
            if not self.ensure_ready():
                return []
            # Return tasks from MongoDB
            cursor = self.tasks.find({"status": {"$ne": "completed"}})
            tasks = list(cursor)
            logger.info(f"Retrieved {len(tasks)} active tasks from MongoDB")
            
            # Ensure each task has a task_id field
            for task in tasks:
                if 'task_id' not in task and '_id' in task:
                    task['task_id'] = str(task['_id'])
                    
            return tasks
        except Exception as e:
            logger.error(f"Error getting active tasks from MongoDB: {e}")
            # Fallback to empty list
            return []

    def get_employees(self):
        """Get all employees from MongoDB"""
        try:
            if not self.ensure_ready():
                return []
            # Get all employees
            employees = list(self.employees.find())
            return employees
        except Exception as e:
            logger.error(f"Error getting employees from MongoDB: {e}")
            return []
    
    def add_employee(self, name: str, chat_id: str) -> Tuple[bool, str, Dict]:
        """
        Add a new employee to the database
        
        Args:
            name: Employee name
            chat_id: Employee chat ID
            
        Returns:
            Tuple[bool, str, Dict]: (success, message, employee_data)
        """
        try:
            if not self.ensure_ready():
                return False, "Database connection error", {}
            existing_employee = self.employees.find_one({'chat_id': chat_id})
            if existing_employee:
                return False, f"Employee with chat ID {chat_id} already exists", existing_employee
            
            # Add employee to database
            employee_data = {
                'name': name,
                'chat_id': chat_id,
                'created_at': datetime.now()
            }
            
            self.employees.update_one(
                {'chat_id': chat_id},
                {'$set': employee_data},
                upsert=True
            )
            
            logger.info(f"Added new employee: {name} with chat ID {chat_id}")
            return True, "Employee added successfully", employee_data
            
        except Exception as e:
            error_msg = f"Error adding employee: {e}"
            logger.error(error_msg)
            return False, error_msg, {}
    
    def remove_employee(self, chat_id: str) -> Tuple[bool, str, Dict]:
        """
        Remove an employee from the database
        
        Args:
            chat_id: Employee chat ID
            
        Returns:
            Tuple[bool, str, Dict]: (success, message, removed_employee_data)
        """
        try:
            if not self.ensure_ready():
                return False, "Database connection error", {}
            existing_employee = self.employees.find_one({'chat_id': chat_id})
            if not existing_employee:
                return False, f"No employee found with chat ID {chat_id}", {}
            
            # Remove employee from database
            result = self.employees.delete_one({'chat_id': chat_id})
            
            if result.deleted_count > 0:
                logger.info(f"Removed employee: {existing_employee['name']} with chat ID {chat_id}")
                return True, "Employee removed successfully", existing_employee
            else:
                return False, f"Failed to remove employee with chat ID {chat_id}", {}
                
        except Exception as e:
            error_msg = f"Error removing employee: {e}"
            logger.error(error_msg)
            return False, error_msg, {}
    
    def get_employee(self, chat_id: str) -> Optional[Dict]:
        """
        Get an employee by chat ID
        
        Args:
            chat_id: Employee chat ID
            
        Returns:
            Optional[Dict]: Employee data or None if not found
        """
        try:
            if not self.ensure_ready():
                return None
            employee = self.employees.find_one({'chat_id': str(chat_id)})
            return employee
            
        except Exception as e:
            logger.error(f"Error getting employee: {e}")
            return None
    
    def get_employee_tasks(self, employee_id):
        """Get all tasks assigned to a specific employee from MongoDB"""
        try:
            if not self.ensure_ready():
                return []
            # First, find the employee name from the chat_id
            employee_name = None
            employee = self.employees.find_one({"chat_id": str(employee_id)})
            
            if employee:
                employee_name = employee.get('name')
                logger.info(f"Found employee name: {employee_name} for chat_id: {employee_id}")
            
            if not employee_name:
                logger.warning(f"No employee found with chat_id: {employee_id}")
                return []
            
            # Find tasks where this employee is in the employees array
            cursor = self.tasks.find({"employees": employee_name, "status": {"$ne": "completed"}})
            tasks = list(cursor)
            
            # Ensure each task has a task_id field
            for task in tasks:
                if 'task_id' not in task and '_id' in task:
                    task['task_id'] = str(task['_id'])
            
            logger.info(f"Retrieved {len(tasks)} tasks for employee: {employee_name}")
            return tasks
            
        except Exception as e:
            logger.error(f"Error getting employee tasks: {e}")
            return []

    # Inquiry operations
    def add_inquiry(self, task_id: int, employee: str, message: str) -> Dict:
        """Add an inquiry to a task."""
        inquiry = {
            'task_id': task_id,
            'employee': employee,
            'message': message,
            'created_at': datetime.now(),
        }
        result = self.inquiries.insert_one(inquiry)
        self.tasks.update_one(
            {'task_id': task_id},
            {'$push': {'inquiries': result.inserted_id}},
        )
        return inquiry
    
    def add_clarification(self, task_id: int, message: str) -> Dict:
        """Add a clarification to a task."""
        clarification = {
            'task_id': task_id,
            'message': message,
            'created_at': datetime.now(),
        }
        self.tasks.update_one(
            {'task_id': task_id},
            {'$push': {'clarifications': clarification}},
        )
        return clarification
    
    # Notification operations
    def add_notification(self, from_id: str, message: str) -> Dict:
        """Add a notification to the database or in-memory storage"""
        notification = {
            'from_id': from_id,
            'message': message,
            'created_at': datetime.now(),
            'status': 'pending'
        }
        
        self.notifications.insert_one(notification)
        return notification
    
    def get_pending_notifications(self) -> List[Dict]:
        """Get pending notifications."""
        if not self.ensure_ready():
            return []
        return list(self.notifications.find({'status': 'pending'}))
    
    def is_connected(self) -> bool:
        """Check if MongoDB is connected and operational"""
        if self.client is None or self.db is None:
            if self.connect():
                return True
            return False

        try:
            # Try to ping the database
            ping_result = self.client.admin.command('ping')
            is_ok = ping_result.get('ok', 0) == 1
            
            if is_ok:
                self._init_collections()
                try:
                    server_info = self.client.server_info()
                    self.connection_status["server_info"] = {
                        "version": server_info.get('version', 'unknown'),
                        "host": server_info.get('host', 'unknown'),
                        "connections": server_info.get('connections', {})
                    }
                except Exception:
                    pass
                    
                self.connection_status["status"] = "connected"
                self.connection_status["error"] = None
            
            return is_ok
        except Exception as e:
            error_msg = f"Connection check failed: {str(e)}"
            logger.error(error_msg)
            self.connection_status["status"] = "error"
            self.connection_status["error"] = error_msg
            # MongoDB connection failed, but we'll try again later
            return False
    
    # Custom message operations
    async def save_message(self, message_id: int, content: str, sent_by: str) -> Dict:
        message = {
            'message_id': message_id,
            'content': content,
            'sent_by': sent_by,
            'created_at': datetime.now()
        }
        
        self.messages.insert_one(message)
        return message

    def get_connection_details(self) -> Dict[str, Any]:
        """Get detailed connection information for diagnostics"""
        return self.connection_status

    async def try_reconnect(self) -> bool:
        """Force a reconnection attempt to MongoDB."""
        logger.info("Forcing reconnection attempt to MongoDB")
        self.reconnect_attempts = 0
        self.last_connection_attempt = None
        return self.connect()

    async def migrate_memory_to_db(self) -> Tuple[bool, int]:
        """No-op: in-memory fallback was removed."""
        return False, 0

# Global database instance
db = MongoDB()
