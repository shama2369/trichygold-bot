import os
from datetime import datetime
from typing import Dict, List, Optional
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
import logging
import ssl
import certifi

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class MongoDB:
    def __init__(self):
        try:
            # Get MongoDB URI from environment variables
            mongodb_uri = os.getenv('MONGODB_URI')
            
            if not mongodb_uri:
                logger.error("MONGODB_URI environment variable not set")
                raise ValueError("MONGODB_URI environment variable not set")
            
            # Configure MongoDB client with SSL options
            # Parse connection string to check if it already contains SSL params
            if '?' in mongodb_uri and ('ssl=true' in mongodb_uri.lower() or 'tls=true' in mongodb_uri.lower()):
                # SSL params already in URI, use as is
                self.client = MongoClient(
                    mongodb_uri,
                    connectTimeoutMS=30000,
                    socketTimeoutMS=30000,
                    serverSelectionTimeoutMS=30000,
                    retryWrites=True,
                    w="majority"
                )
                logger.info("Using SSL parameters from connection string")
            else:
                # Add SSL params to client constructor
                self.client = MongoClient(
                    mongodb_uri,
                    tls=True,
                    tlsAllowInvalidCertificates=True,  # More permissive for troubleshooting
                    connectTimeoutMS=30000,
                    socketTimeoutMS=30000,
                    serverSelectionTimeoutMS=30000,
                    retryWrites=True,
                    w="majority"
                )
                logger.info("Using explicit SSL parameters")
            
            # Try to connect to MongoDB
            try:
                # Test the connection with a ping command
                ping_result = self.client.admin.command('ping')
                
                # If ping succeeds, set up collections
                self.db: Database = self.client["trichygold_bot"]
                self.tasks: Collection = self.db["tasks"]
                self.inquiries: Collection = self.db["inquiries"]
                self.notifications: Collection = self.db["notifications"]
                self.messages: Collection = self.db["messages"]
                
                # Try a simple database operation to verify full connectivity
                test_result = self.db.command('buildInfo')
                
                # Get server info for detailed logging
                server_info = self.client.server_info()
                
                logger.info(f"Successfully connected to MongoDB:")
                logger.info(f"  - Server: {server_info.get('host', 'unknown')}")
                logger.info(f"  - Version: {server_info.get('version', 'unknown')}")
                logger.info(f"  - Database: {self.db.name}")
                self.in_memory_mode = False
            except Exception as e:
                logger.error(f"Failed to connect to MongoDB: {e}")
                logger.warning("Using in-memory storage as fallback")
                self.in_memory_mode = True
                self.tasks_data = []
                self.inquiries_data = []
                self.notifications_data = []
                self.messages_data = []
            
            # Collections
            if not self.in_memory_mode:
                # Create indexes
                self.tasks.create_index('task_id', unique=True)
                self.inquiries.create_index('inquiry_id', unique=True)
        
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            # Create fallback in-memory storage for development/testing
            self.client = None
            self.in_memory_mode = True
            self.tasks_data = []
            self.inquiries_data = []
            self.notifications_data = []
            self.messages_data = []
            logger.warning("Using in-memory storage as fallback")
        
    # Task operations
    async def create_task(self, task_id: int, task: str, employees: List[str], reminder_interval: int) -> Dict:
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
            await self.tasks.insert_one(task_doc)
            
        return task_doc
    
    async def get_task(self, task_id: int) -> Optional[Dict]:
        if self.in_memory_mode:
            for task in self.tasks_data:
                if task['task_id'] == task_id:
                    return task
            return None
        else:
            return await self.tasks.find_one({'task_id': task_id})
    
    async def update_task_status(self, task_id: int, status: str, completed_by: str = None) -> bool:
        if self.in_memory_mode:
            for task in self.tasks_data:
                if task['task_id'] == task_id:
                    task['status'] = status
                    task['completed_at'] = datetime.now()
                    task['completed_by'] = completed_by
                    return True
            return False
        else:
            update = {
                '$set': {
                    'status': status,
                    'completed_at': datetime.now(),
                    'completed_by': completed_by
                }
            }
            result = await self.tasks.update_one({'task_id': task_id}, update)
            return result.modified_count > 0
    
    async def get_active_tasks(self) -> List[Dict]:
        if self.in_memory_mode:
            return [task for task in self.tasks_data if task['status'] == 'active']
        else:
            return await self.tasks.find({'status': 'active'}).to_list(length=None)
    
    # Inquiry operations
    async def add_inquiry(self, task_id: int, employee: str, message: str) -> Dict:
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
            await self.inquiries.insert_one(inquiry)
            # Update task with inquiry reference
            await self.tasks.update_one(
                {'task_id': task_id},
                {'$push': {'inquiries': inquiry['_id']}}
            )
            
        return inquiry
    
    async def add_clarification(self, task_id: int, message: str) -> Dict:
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
            # Update task with clarification
            await self.tasks.update_one(
                {'task_id': task_id},
                {'$push': {'clarifications': clarification}}
            )
            
        return clarification
    
    # Notification operations
    async def add_notification(self, from_id: str, message: str) -> Dict:
        notification = {
            'from_id': from_id,
            'message': message,
            'created_at': datetime.now(),
            'status': 'pending'
        }
        
        if self.in_memory_mode:
            self.notifications_data.append(notification)
        else:
            await self.notifications.insert_one(notification)
            
        return notification
    
    async def get_pending_notifications(self) -> List[Dict]:
        if self.in_memory_mode:
            return [n for n in self.notifications_data if n['status'] == 'pending']
        else:
            return await self.notifications.find({'status': 'pending'}).to_list(length=None)
    
    def is_connected(self) -> bool:
        """Check if MongoDB is connected and operational"""
        if self.in_memory_mode:
            return False
            
        try:
            # Try to ping the database
            ping_result = self.client.admin.command('ping')
            return ping_result.get('ok', 0) == 1
        except Exception as e:
            logger.error(f"Connection check failed: {e}")
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
            await self.messages.insert_one(message)
            
        return message

# Global database instance
db = MongoDB()
