import os
from datetime import datetime
from typing import Dict, List, Optional
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

class MongoDB:
    def __init__(self):
        self.client = MongoClient(os.getenv('MONGODB_URI'))
        self.db: Database = self.client['trichygold_bot']
        
        # Collections
        self.tasks: Collection = self.db['tasks']
        self.inquiries: Collection = self.db['inquiries']
        self.notifications: Collection = self.db['notifications']
        self.messages: Collection = self.db['messages']
        
        # Create indexes
        self.tasks.create_index('task_id', unique=True)
        self.inquiries.create_index('inquiry_id', unique=True)
        
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
        await self.tasks.insert_one(task_doc)
        return task_doc
    
    async def get_task(self, task_id: int) -> Optional[Dict]:
        return await self.tasks.find_one({'task_id': task_id})
    
    async def update_task_status(self, task_id: int, status: str, completed_by: str = None) -> bool:
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
        return await self.tasks.find({'status': 'active'}).to_list(length=None)
    
    # Inquiry operations
    async def add_inquiry(self, task_id: int, employee: str, message: str) -> Dict:
        inquiry = {
            'task_id': task_id,
            'employee': employee,
            'message': message,
            'created_at': datetime.now()
        }
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
        await self.notifications.insert_one(notification)
        return notification
    
    async def get_pending_notifications(self) -> List[Dict]:
        return await self.notifications.find({'status': 'pending'}).to_list(length=None)
    
    # Custom message operations
    async def save_message(self, message_id: int, content: str, sent_by: str) -> Dict:
        message = {
            'message_id': message_id,
            'content': content,
            'sent_by': sent_by,
            'created_at': datetime.now()
        }
        await self.messages.insert_one(message)
        return message

# Global database instance
db = MongoDB()
