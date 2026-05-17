import os
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError, OperationFailure
import logging
import ssl
import certifi
import time
import asyncio
import urllib.parse

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
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
            
    def _connect_to_mongodb(self) -> bool:
        """Attempt to connect to MongoDB with retry logic"""
        try:
            # Get MongoDB URI from environment variables
            mongodb_uri = get_mongodb_uri()
            self.uri = mongodb_uri
            
            if not mongodb_uri:
                logger.error("MONGODB_URI (or MONGO_URI) environment variable not set")
                self.connection_error = "MONGODB_URI (or MONGO_URI) environment variable not set"
                # MongoDB connection failed, but we'll try again later
                
                # Update connection status
                self.connection_status = {
                    "status": "error",
                    "last_attempt": datetime.now(),
                    "error": self.connection_error,
                    "server_info": None,
                    "reconnect_attempts": self.reconnect_attempts
                }
                
                logger.warning("MONGODB_URI not set. Falling back to in-memory storage mode.")
                return False
            
            mongodb_uri = _encode_mongodb_uri(mongodb_uri)
            self.uri = mongodb_uri
            
            # Update connection status
            self.last_connection_attempt = datetime.now()
            self.connection_status["last_attempt"] = self.last_connection_attempt
            self.connection_status["status"] = "connecting"
            
            # Connect with minimal parameters but ensure SSL certificate validation
            logger.info("Attempting to connect to MongoDB...")
            self.client = MongoClient(
                mongodb_uri,
                tlsCAFile=certifi.where(),  # Add SSL certificate validation
                connectTimeoutMS=30000,
                socketTimeoutMS=30000,
                serverSelectionTimeoutMS=30000,
                retryWrites=True,  # Enable retry for write operations
                w="majority"  # Wait for write acknowledgment from majority of replicas
            )
            logger.info("MongoDB client initialized")
            
            # Try to connect to MongoDB
            try:
                # Log connection attempt details (safely without credentials)
                if '@' in mongodb_uri:
                    uri_parts = mongodb_uri.split('@')
                    if len(uri_parts) > 1 and '/' in uri_parts[1]:
                        host_part = uri_parts[1].split('/')[0]
                        logger.info(f"MongoDB URI pattern: {host_part}")
                
                logger.info(f"MongoDB client options: connectTimeoutMS=30000, socketTimeoutMS=30000, serverSelectionTimeoutMS=30000")
                
                # Ping the database to check connection
                logger.info("Attempting to ping MongoDB server...")
                self.client.admin.command('ping')
                
                # Get server info for detailed logging
                server_info = self.client.server_info()
                logger.info(f"Successfully connected to MongoDB. Server version: {server_info.get('version', 'unknown')}")
                
                uri_parts = re.match(
                    r'mongodb(?:\+srv)?://(?:.*@)?([^/]+)(?:/([^?]+))?', mongodb_uri
                )
                db_name = (
                    uri_parts.group(2) if uri_parts and uri_parts.group(2) else 'trichygold'
                )
                self.db = self.client[db_name]
                self._init_collections()
                
                # Set storage mode flag
                # MongoDB connection successful
                self.connection_error = None
                self.reconnect_attempts = 0
                
                # Update connection status
                self.connection_status = {
                    "status": "connected",
                    "last_attempt": self.last_connection_attempt,
                    "error": None,
                    "server_info": {
                        "version": server_info.get('version', 'unknown'),
                        "host": server_info.get('host', 'unknown'),
                        "connections": server_info.get('connections', {})
                    },
                    "reconnect_attempts": self.reconnect_attempts
                }
                
                logger.info("Using MongoDB for storage")
                
                # Create indexes
                self.tasks.create_index('task_id', unique=True)
                self.inquiries.create_index('inquiry_id', unique=True)
                
                return True
                
            except (ConnectionFailure, ServerSelectionTimeoutError, OperationFailure) as e:
                error_msg = f"Failed to connect to MongoDB: {str(e)}"
                logger.error(error_msg)
                self.connection_error = error_msg
                # MongoDB connection failed, but we'll try again later
                
                # Update connection status
                self.connection_status = {
                    "status": "error",
                    "last_attempt": self.last_connection_attempt,
                    "error": error_msg,
                    "server_info": None,
                    "reconnect_attempts": self.reconnect_attempts
                }
                
                logger.warning("Falling back to in-memory storage mode")
                return False
                
        except Exception as e:
            error_msg = f"Unexpected error connecting to MongoDB: {str(e)}"
            logger.error(error_msg)
            self.connection_error = error_msg
            # MongoDB connection failed, but we'll try again later
            
            # Update connection status
            self.connection_status = {
                "status": "error",
                "last_attempt": self.last_connection_attempt,
                "error": error_msg,
                "server_info": None,
                "reconnect_attempts": self.reconnect_attempts
            }
            
            logger.warning("Falling back to in-memory storage mode due to unexpected error")
            return False
            
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
        
        if False:  # MongoDB only mode
            self.tasks_data.append(task_doc)
        else:
            # Use insert_one without await - pymongo operations are not coroutines
            self.tasks.insert_one(task_doc)
        
        return task_doc
    
    def get_task(self, task_id: int) -> Optional[Dict]:
        """Get a task by its ID from database or in-memory storage"""
        if False:  # MongoDB only mode
            for task in self.tasks_data:
                if task['task_id'] == task_id:
                    return task
            return None
        else:
            # MongoDB operations are not coroutines, so no await needed
            return self.tasks.find_one({'task_id': task_id})
    
    def update_task_status(self, task_id: int, status: str, completed_by: str = None) -> bool:
        """Update a task's status in database or in-memory storage"""
        if False:  # MongoDB only mode
            # Update task in in-memory storage
            for task in self.tasks_data:
                if task.get('task_id') == task_id:
                    task['status'] = status
                    if status == 'completed' and completed_by:
                        task['completed_at'] = datetime.now()
                        task['completed_by'] = completed_by
                    return True
            return False
        else:
            # Update task in MongoDB
            update = {
                '$set': {
                    'status': status,
                    'completed_at': datetime.now(),
                    'completed_by': completed_by
                }
            }
            # Don't use await with update_one
            result = self.tasks.update_one({'task_id': task_id}, update)
            return result.modified_count > 0
    
    def get_active_tasks(self) -> List[Dict]:
        """Get all active tasks from MongoDB"""
        try:
            # Ensure we have a valid connection
            if not self.is_connected():
                logger.warning("MongoDB not connected. Attempting to reconnect...")
                self.connect()
                
            if not hasattr(self, 'tasks') or self.tasks is None:
                self.tasks = self.db.tasks
                
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
            if not self.is_connected():
                logger.warning("Cannot get employees: MongoDB not connected")
                return []
                
            # Make sure we have the employees collection
            if not hasattr(self, 'employees') or self.employees is None:
                self.employees = self.db.employees
                
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
            if not self.is_connected():
                return False, "Database connection error", {}
                
            # Make sure we have the employees collection
            if not hasattr(self, 'employees') or self.employees is None:
                self.employees = self.db.employees
                
            # Check if employee already exists
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
            if not self.is_connected():
                return False, "Database connection error", {}
                
            # Make sure we have the employees collection
            if not hasattr(self, 'employees') or self.employees is None:
                self.employees = self.db.employees
                
            # Check if employee exists
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
            if not self.is_connected():
                logger.warning("Cannot get employee: MongoDB not connected")
                return None
                
            # Make sure we have the employees collection
            if not hasattr(self, 'employees') or self.employees is None:
                self.employees = self.db.employees
                
            # Find employee by chat_id
            employee = self.employees.find_one({'chat_id': str(chat_id)})
            return employee
            
        except Exception as e:
            logger.error(f"Error getting employee: {e}")
            return None
    
    def get_employee_tasks(self, employee_id):
        """Get all tasks assigned to a specific employee from MongoDB"""
        try:
            # Ensure we have a valid connection
            if not self.is_connected():
                logger.warning("MongoDB not connected. Attempting to reconnect...")
                self.connect()
                
            # Make sure we have the tasks and employees collections
            if not hasattr(self, 'tasks') or self.tasks is None:
                self.tasks = self.db.tasks
                
            if not hasattr(self, 'employees') or self.employees is None:
                self.employees = self.db.employees
            
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
        """Add an inquiry to a task in database or in-memory storage"""
        # ... (rest of the code remains the same)
        inquiry = {
            'task_id': task_id,
            'employee': employee,
            'message': message,
            'created_at': datetime.now()
        }
        
        if False:  # MongoDB only mode
            self.inquiries_data.append(inquiry)
            # Find and update the task in memory
            for task in self.tasks_data:
                if task['task_id'] == task_id:
                    if 'inquiries' not in task:
                        task['inquiries'] = []
                    task['inquiries'].append(inquiry)
                    break
        else:
            # Use insert_one without await
            result = self.inquiries.insert_one(inquiry)
            # Update task with inquiry reference - don't use await
            self.tasks.update_one(
                {'task_id': task_id},
                {'$push': {'inquiries': result.inserted_id}}
            )
            
        return inquiry
    
    def add_clarification(self, task_id: int, message: str) -> Dict:
        """Add a clarification to a task in database or in-memory storage"""
        clarification = {
            'task_id': task_id,
            'message': message,
            'created_at': datetime.now()
        }
        
        if False:  # MongoDB only mode
            # Find and update the task in memory
            for task in self.tasks_data:
                if task['task_id'] == task_id:
                    if 'clarifications' not in task:
                        task['clarifications'] = []
                    task['clarifications'].append(clarification)
                    break
        else:
            # Update task with clarification - don't use await
            self.tasks.update_one(
                {'task_id': task_id},
                {'$push': {'clarifications': clarification}}
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
        
        if False:  # MongoDB only mode
            self.notifications_data.append(notification)
        else:
            # Use insert_one without await
            self.notifications.insert_one(notification)
            
        return notification
    
    def get_pending_notifications(self) -> List[Dict]:
        """Get pending notifications from database or in-memory storage"""
        if False:  # MongoDB only mode
            return [n for n in self.notifications_data if n['status'] == 'pending']
        else:
            # Convert cursor to list manually
            cursor = self.notifications.find({'status': 'pending'})
            result = []
            for doc in cursor:
                result.append(doc)
            return result
    
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
        
        if False:  # MongoDB only mode
            self.messages_data.append(message)
        else:
            # Use insert_one without await
            self.messages.insert_one(message)
            
        return message

    def get_connection_details(self) -> Dict[str, Any]:
        """Get detailed connection information for diagnostics"""
        return self.connection_status

    async def try_reconnect(self) -> bool:
        """Force a reconnection attempt to MongoDB"""
        logger.info("Forcing reconnection attempt to MongoDB")
        self.reconnect_attempts = 0
        self.last_connection_attempt = None
        return self._connect_to_mongodb()

    async def migrate_memory_to_db(self) -> Tuple[bool, int]:
        """Migrate in-memory data to MongoDB if connection is restored"""
        if not self.is_connected():
            return False, 0
            
        try:
            # We have a connection but we're still in memory mode
            # This means we need to migrate data and switch modes
            migrated_count = 0
            
            # Migrate tasks
            if self.tasks_data:
                for task in self.tasks_data:
                    await self.tasks.update_one(
                        {"task_id": task["task_id"]},
                        {"$set": task},
                        upsert=True
                    )
                    migrated_count += 1
                    
            # Migrate inquiries
            if self.inquiries_data:
                for inquiry in self.inquiries_data:
                    await self.inquiries.update_one(
                        {"inquiry_id": inquiry.get("inquiry_id")},
                        {"$set": inquiry},
                        upsert=True
                    )
                    migrated_count += 1
                    
            # Migrate notifications
            if self.notifications_data:
                for notification in self.notifications_data:
                    await self.notifications.insert_one(notification)
                    migrated_count += 1
                    
            # Migrate messages
            if self.messages_data:
                for message in self.messages_data:
                    await self.messages.insert_one(message)
                    migrated_count += 1
                    
            # Migration successful
            logger.info("Switched to database mode exclusively")
            logger.info(f"Successfully migrated {migrated_count} items from memory to MongoDB")
            
            return True, migrated_count
        except Exception as e:
            logger.error(f"Failed to migrate in-memory data to MongoDB: {e}")
            return False, 0

# Global database instance
db = MongoDB()
