import os
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

class MongoDB:
    def __init__(self, uri=None):
        self.uri = uri or os.getenv('MONGODB_URI')
        self.client = None
        self.db = None
        self.tasks = None
        self.inquiries = None
        self.notifications = None
        self.messages = None
        self.connect()
        self.connection_status = {
            "status": "disconnected",
            "last_attempt": None,
            "error": None,
            "server_info": None,
            "reconnect_attempts": 0
        }
        
        # Initialize in-memory fallback storage
        self.tasks_data = []
        self.inquiries_data = []
        self.notifications_data = []
        self.messages_data = []
        
        # Attempt initial connection
        self._connect_to_mongodb()
        
        # Start background reconnection task if needed
        if self.in_memory_mode:
            logger.warning("Using in-memory storage as fallback")
            # We'll handle reconnection attempts in the is_connected method

    def _connect_to_mongodb(self) -> bool:
        """Attempt to connect to MongoDB with retry logic"""
        try:
            # Get MongoDB URI from environment variables
            mongodb_uri = os.getenv('MONGODB_URI')
            
            if not mongodb_uri:
                logger.error("MONGODB_URI environment variable not set")
                self.connection_error = "MONGODB_URI environment variable not set"
                self.in_memory_mode = True
                
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
            
            # Properly encode username and password in the URI
            if '@' in mongodb_uri:
                try:
                    # Split the URI into components
                    prefix, rest = mongodb_uri.split('://', 1)
                    auth_part, host_part = rest.split('@', 1)
                    
                    # Check if auth part contains username and password
                    if ':' in auth_part:
                        username, password = auth_part.split(':', 1)
                        # URL encode the username and password
                        encoded_username = urllib.parse.quote_plus(username)
                        encoded_password = urllib.parse.quote_plus(password)
                        # Reconstruct the URI
                        mongodb_uri = f"{prefix}://{encoded_username}:{encoded_password}@{host_part}"
                        logger.info("URI components have been properly URL-encoded")
                except Exception as e:
                    logger.warning(f"Failed to encode URI components: {str(e)}")
            
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
                
                # Set up database and collections
                self.db = self.client.get_database("trichygold_bot")
                self.tasks = self.db.get_collection("tasks")
                self.inquiries = self.db.get_collection("inquiries")
                self.notifications = self.db.get_collection("notifications")
                self.messages = self.db.get_collection("messages")
                
                # Set storage mode flag
                self.in_memory_mode = False
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
                self.in_memory_mode = True
                
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
            self.in_memory_mode = True
            
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
        
        if self.in_memory_mode:
            self.tasks_data.append(task_doc)
        else:
            # Use insert_one without await - pymongo operations are not coroutines
            self.tasks.insert_one(task_doc)
        
        return task_doc
    
    def get_task(self, task_id: int) -> Optional[Dict]:
        """Get a task by its ID from database or in-memory storage"""
        if self.in_memory_mode:
            for task in self.tasks_data:
                if task['task_id'] == task_id:
                    return task
            return None
        else:
            # MongoDB operations are not coroutines, so no await needed
            return self.tasks.find_one({'task_id': task_id})
    
    def update_task_status(self, task_id: int, status: str, completed_by: str = None) -> bool:
        """Update a task's status in database or in-memory storage"""
        if self.in_memory_mode:
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
            # Ensure we have a valid connection
            if not self.is_connected():
                logger.warning("MongoDB not connected. Attempting to reconnect...")
                self.connect()
            
            # Make sure we have the employees collection
            if not hasattr(self, 'employees') or self.employees is None:
                self.employees = self.db.employees
                
            # Get all employees from MongoDB
            employees = list(self.employees.find({}))
            logger.info(f"Retrieved {len(employees)} employees from MongoDB")
            
            return employees
        except Exception as e:
            logger.error(f"Error getting employees from MongoDB: {e}")
            return []
    
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
        
        if self.in_memory_mode:
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
        
        if self.in_memory_mode:
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
        
        if self.in_memory_mode:
            self.notifications_data.append(notification)
        else:
            # Use insert_one without await
            self.notifications.insert_one(notification)
            
        return notification
    
    def get_pending_notifications(self) -> List[Dict]:
        """Get pending notifications from database or in-memory storage"""
        if self.in_memory_mode:
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
        if self.in_memory_mode:
            # Check if we should attempt reconnection
            current_time = datetime.now()
            if (self.last_connection_attempt is None or 
                (current_time - self.last_connection_attempt).total_seconds() > self.reconnect_delay * (2 ** min(self.reconnect_attempts, 5))):
                
                # Exponential backoff for reconnection attempts
                if self.reconnect_attempts < self.max_reconnect_attempts:
                    logger.info(f"Attempting to reconnect to MongoDB (attempt {self.reconnect_attempts + 1}/{self.max_reconnect_attempts})")
                    self.reconnect_attempts += 1
                    self.connection_status["reconnect_attempts"] = self.reconnect_attempts
                    
                    # Try to reconnect
                    if self._connect_to_mongodb():
                        logger.info("Successfully reconnected to MongoDB")
                        return True
                else:
                    # Reset reconnect attempts counter after max attempts to allow future retries
                    if (current_time - self.last_connection_attempt).total_seconds() > 300:  # 5 minutes
                        self.reconnect_attempts = 0
                        self.connection_status["reconnect_attempts"] = 0
            
            return False
            
        try:
            # Try to ping the database
            ping_result = self.client.admin.command('ping')
            is_ok = ping_result.get('ok', 0) == 1
            
            if is_ok:
                # Update server info if connection is successful
                try:
                    server_info = self.client.server_info()
                    self.connection_status["server_info"] = {
                        "version": server_info.get('version', 'unknown'),
                        "host": server_info.get('host', 'unknown'),
                        "connections": server_info.get('connections', {})
                    }
                except Exception:
                    # If we can't get server info but ping worked, that's still a success
                    pass
                    
                self.connection_status["status"] = "connected"
                self.connection_status["error"] = None
            
            return is_ok
        except Exception as e:
            error_msg = f"Connection check failed: {str(e)}"
            logger.error(error_msg)
            self.connection_status["status"] = "error"
            self.connection_status["error"] = error_msg
            self.in_memory_mode = True
            return False
    
    # Custom message operations
    async def save_message(self, message_id: int, content: str, sent_by: str) -> Dict:
        message = {
            'message_id': message_id,
            'content': content,
            'sent_by': sent_by,
            'created_at': datetime.now()
        }
        
        if self.in_memory_mode:
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
        if not self.is_connected() or not self.in_memory_mode:
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
                    
            # Switch to database mode
            self.in_memory_mode = False
            logger.info(f"Successfully migrated {migrated_count} items from memory to MongoDB")
            
            return True, migrated_count
        except Exception as e:
            logger.error(f"Failed to migrate in-memory data to MongoDB: {e}")
            return False, 0

# Global database instance
db = MongoDB()
