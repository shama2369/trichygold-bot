import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
from datetime import datetime, time
import pytz
import logging
from typing import Dict, List, Optional
from quart import Quart, request
import uvicorn
import os
import aiohttp
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Get environment variables
BOT_TOKEN = os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN')
# Set YOUR_ID to a default value that matches your Telegram ID
YOUR_ID = os.getenv('ADMIN_ID', '1341853859')  # Default to shameem's ID

# Bot Configuration
EMPLOYEES = {
    'shameem': '1341853859',
    'rehan': '1475715464',
    
}

# Initialize database and bot
from database import db
application = Application.builder().token(BOT_TOKEN).build()
app = Quart(__name__)

# Global state management
TASKS: Dict[int, dict] = {}  # task_id: task_info
INQUIRIES: Dict[int, dict] = {}  # inquiry_id: inquiry_info
NOTIFICATIONS: Dict[int, dict] = {}  # notification_id: notification_info
CUSTOM_MESSAGES: Dict[int, dict] = {}  # message_id: message_info
CONTEXT = {}
CONCERN_CONTEXT = {}
TASK_STATUS = {}
ACTIVE_EMPLOYEES = {}

# Fixed messages for different times
FIXED_MESSAGES = {
    "morning": "🌅 Good Morning TrichyGold Team!\n\nToday's Focus:\n• Check daily targets\n• Review inventory\n• Plan customer interactions",
    "afternoon": "🌞 Afternoon Update Time!\n\nMid-day Checklist:\n• Sales progress\n• Customer feedback\n• Stock updates",
    "evening": "🌆 Evening Check-in!\n\nEnd-day Tasks:\n• Complete pending work\n• Update records\n• Prepare for tomorrow",
    "night": "🌙 Day End Summary!\n\nBefore Closing:\n• Final counts\n• Security check\n• Tomorrow's preparation"
}

# Task counter for unique IDs
task_counter = 0

# Helper Functions
def get_employee_name(chat_id):
    for name, eid in EMPLOYEES.items():
        if eid == str(chat_id):
            return name
    return None

def format_task_message(task, minutes):
    return f"📋 New Task Assigned!\n\nTask: {task}\nReminder: Every {minutes} minutes\n\nPlease reply to this message with:\n• Text updates\n• Voice messages\n• Files/documents\n• 'done' when completed"

def create_task_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("Mark as Done ✅", callback_data="done"),
            InlineKeyboardButton("Ask for Clarification ❓", callback_data="clarify")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# Command Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    chat_id = str(update.message.chat_id)
    user_name = update.message.from_user.first_name
    
    # Log the start command for debugging
    logger.info(f"Start command received from user {chat_id} ({user_name})")
    
    if chat_id == YOUR_ID:
        welcome_message = (
            f"👋 Welcome to TrichyGold Task Manager!\n\n"
            f"🔑 You are logged in as ADMIN\n"
            f"Your Chat ID: {chat_id}\n\n"
            f"Available Commands:\n"
            f"/assign - Assign tasks (single/group)\n"
            f"/done - View & manage active tasks\n"
            f"/clarify - Add details to tasks\n"
            f"/broadcast - Send custom message to all\n"
            f"/list_employees - View all employees\n"
            f"/help - Show this message"
        )
    else:
        employee_name = get_employee_name(chat_id)
        if employee_name:
            welcome_message = (
                f"👋 Welcome {user_name}!\n\n"
                f"You are registered as: {employee_name}\n"
                f"Your Chat ID: {chat_id}\n\n"
                f"Available Commands:\n"
                f"/inquire - Ask questions about tasks\n"
                f"/taskdone - Mark tasks as completed\n"
                f"/notify - Send notice to admin\n"
                f"/mytasks - View your active tasks\n"
                f"/help - Show this message"
            )
        else:
            welcome_message = (
                f"👋 Welcome {user_name}!\n\n"
                f"⚠️ You are not registered.\n"
                f"Your Chat ID: {chat_id}\n\n"
                f"Please contact admin to get registered."
            )
    
    await update.message.reply_text(welcome_message)

async def assign_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /assign command for task assignment"""
    if str(update.message.chat_id) != YOUR_ID:
        await update.message.reply_text("❌ Only admin can assign tasks!")
        return
    
    try:
        args = context.args
        if len(args) < 2:
            await update.message.reply_text(
                "❌ Usage: /assign employee1,employee2 <task> [minutes]\n"
                "Example: /assign rehan,shameem Check inventory 30"
            )
            return
        
        # Parse employees
        employees = [emp.strip() for emp in args[0].split(',')]
        invalid_employees = [emp for emp in employees if emp not in EMPLOYEES]
        if invalid_employees:
            await update.message.reply_text(
                f"❌ Unknown employees: {', '.join(invalid_employees)}\n"
                f"Available: {', '.join(EMPLOYEES.keys())}"
            )
            return
        
        # Parse task and minutes
        if len(args) > 2 and args[-1].isdigit():
            task = ' '.join(args[1:-1])
            minutes = int(args[-1])
        else:
            task = ' '.join(args[1:])
            minutes = 30  # default reminder interval
        
        global task_counter
        task_counter += 1
        task_id = task_counter
        
        # Store task in database
        task_doc = await db.create_task(task_id, task, employees, minutes)
        
        # Also store in global TASKS dictionary for backward compatibility
        global TASKS
        TASKS[task_id] = task_doc
        
        # Send task to each employee
        for employee in employees:
            chat_id = EMPLOYEES[employee]
            keyboard = [
                [
                    InlineKeyboardButton("✅ Mark Done", callback_data=f"taskdone_{task_id}"),
                    InlineKeyboardButton("❓ Ask Question", callback_data=f"inquire_{task_id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Format time in Dubai timezone
            dubai_tz = pytz.timezone('Asia/Dubai')
            created_time = task_doc['created_at']
            if hasattr(created_time, 'astimezone'):
                created_time = created_time.astimezone(dubai_tz).strftime('%I:%M %p')
            else:
                # Handle non-timezone aware datetime objects
                created_time = created_time.strftime('%I:%M %p')
            
            message = (
                f"📋 New Task #{task_id}\n\n"
                f"Task: {task}\n"
                f"Created: {created_time} (UAE)\n"
                f"Reminder: Every {minutes} minutes\n\n"
                f"Use:\n"
                f"• /inquire {task_id} - Ask questions\n"
                f"• /taskdone {task_id} - Mark as completed"
            )
            
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    reply_markup=reply_markup
                )
            except Exception as e:
                logger.error(f"Failed to send task to {employee}: {e}")
        
        await update.message.reply_text(
            f"✅ Task #{task_id} assigned to: {', '.join(employees)}\n"
            f"Task: {task}\n"
            f"Reminders: Every {minutes} minutes"
        )
        
        # Schedule reminder
        if context.job_queue:
            context.job_queue.run_repeating(
                send_task_reminder,
                interval=minutes * 60,
                first=minutes * 60,
                data={'task_id': task_id}
            )
    
    except Exception as e:
        logger.error(f"Error in assign_task: {e}")
        await update.message.reply_text("❌ Failed to assign task. Please try again.")

async def done_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /done command to view active tasks"""
    try:
        chat_id = str(update.message.chat_id)
        
        # Get active tasks from database
        active_tasks = await db.get_active_tasks()
        
        if not active_tasks:
            await update.message.reply_text("📝 No active tasks at the moment.")
            return
            
        # Format tasks based on user role
        if chat_id == YOUR_ID:  # Admin view
            message = "📋 Active Tasks:\n\n"
            for task in active_tasks:
                task_id = task['task_id']
                assignees = task['employees']
                message += (
                    f"Task #{task_id}:\n"
                    f"• Description: {task['task']}\n"
                    f"• Assigned to: {', '.join(assignees)}\n"
                    f"• Time allocated: {task.get('reminder_interval', 'Not specified')} minutes\n\n"
                )
        else:  # Employee view
            employee_name = get_employee_name(chat_id)
            if not employee_name:
                await update.message.reply_text("❌ You are not registered as an employee.")
                return
                
            # Filter tasks for this employee
            employee_tasks = [task for task in active_tasks if employee_name in task['employees']]
            
            if not employee_tasks:
                await update.message.reply_text("📝 You have no active tasks at the moment.")
                return
                
            message = "📋 Your Active Tasks:\n\n"
            for task in employee_tasks:
                task_id = task['task_id']
                message += (
                    f"Task #{task_id}:\n"
                    f"• Description: {task['task']}\n"
                    f"• Time allocated: {task.get('reminder_interval', 'Not specified')} minutes\n"
                )
                # Add buttons for employee actions
                keyboard = [
                    [InlineKeyboardButton("Mark as Done ✅", callback_data=f"taskdone_{task_id}")],
                    [InlineKeyboardButton("Ask Question ❓", callback_data=f"inquire_{task_id}")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(message, reply_markup=reply_markup)
                message = ""  # Reset for next task
                
        if message:  # Send remaining message if any
            await update.message.reply_text(message)
            
    except Exception as e:
        logger.error(f"Error in done_command: {e}")
        await update.message.reply_text("❌ An error occurred while fetching tasks.")

async def clarify_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /clarify command for admin to add details to tasks"""
    try:
        chat_id = str(update.message.chat_id)
        
        if chat_id != YOUR_ID:
            await update.message.reply_text("❌ Only admin can use this command.")
            return
            
        args = context.args
        if not args or not args[0].isdigit():
            await update.message.reply_text(
                "❌ Usage: /clarify <task_id>\n"
                "Then reply with text, voice, or attachments"
            )
            return
            
        task_id = int(args[0])
        if task_id not in TASKS:
            await update.message.reply_text(f"❌ Task #{task_id} not found!")
            return
            
        if TASKS[task_id].get('completed', False):
            await update.message.reply_text(f"❌ Task #{task_id} is already completed. Cannot add clarification.")
            return
            
        # Store context for handling the next message
        context.user_data['clarifying_task'] = task_id
        
        await update.message.reply_text(
            f"📝 Send your clarification for Task #{task_id}\n"
            f"You can send:\n"
            f"• Text message\n"
            f"• Voice message\n"
            f"• Files/documents\n"
            f"• Photos"
        )
            
    except Exception as e:
        logger.error(f"Error in clarify_command: {e}")
        await update.message.reply_text("❌ An error occurred while processing your command.")

async def list_employees_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /list_employees command for admin to view and manage employees"""
    try:
        chat_id = str(update.message.chat_id)
        
        if chat_id != YOUR_ID:
            await update.message.reply_text("❌ Only admin can use this command.")
            return
            
        if not EMPLOYEES:
            await update.message.reply_text(
                "📋 No employees registered.\n"
                "To add an employee, use:\n"
                "/add_employee <name> <telegram_id>"
            )
            return
            
        # Build employee list with task counts
        employee_list = []
        for name, emp_id in EMPLOYEES.items():
            active_tasks = sum(1 for task in TASKS.values() 
                             if name in task.get('employees', []) 
                             and task.get('status') != 'completed')
            total_tasks = sum(1 for task in TASKS.values() 
                            if name in task.get('employees', []))
            employee_list.append(f"👤 {name}\n   📱 ID: {emp_id}\n   📋 Tasks: {active_tasks} active, {total_tasks} total")
        
        message = "📋 Registered Employees:\n\n" + "\n\n".join(employee_list)
        message += "\n\nTo add an employee:\n/add_employee <name> <telegram_id>"
        
        await update.message.reply_text(message)
        
    except Exception as e:
        logger.error(f"Error in list_employees_command: {e}")
        await update.message.reply_text("❌ An error occurred while listing employees.")

async def notify_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /notify command for admin to send notifications about specific tasks"""
    try:
        chat_id = str(update.message.chat_id)
        
        if chat_id != YOUR_ID:
            await update.message.reply_text("❌ Only admin can use this command.")
            return
            
        if not context.args:
            active_tasks = {task_id: task for task_id, task in TASKS.items() 
                          if task.get('status') != 'completed'}
            
            if not active_tasks:
                await update.message.reply_text("📋 No active tasks to notify about.")
                return
                
            task_list = []
            for task_id, task in active_tasks.items():
                employees = ", ".join(task.get('employees', []))
                task_list.append(f"Task #{task_id}: {task['task']}\nAssigned to: {employees}")
            
            message = (
                "To send a notification, use:\n"
                "/notify <task_id> <message>\n\n"
                "📋 Active Tasks:\n\n" + 
                "\n\n".join(task_list)
            )
            await update.message.reply_text(message)
            return
            
        task_id = context.args[0]
        if task_id not in TASKS:
            await update.message.reply_text("❌ Invalid task ID.")
            return
            
        if TASKS[task_id].get('status') == 'completed':
            await update.message.reply_text("❌ Cannot send notification for completed task.")
            return
            
        if len(context.args) < 2:
            await update.message.reply_text("❌ Please provide a notification message.")
            return
            
        notification = " ".join(context.args[1:])
        task = TASKS[task_id]
        
        success_count = 0
        failed_sends = []
        
        for employee_name in task.get('employees', []):
            if employee_name in EMPLOYEES:
                emp_chat_id = EMPLOYEES[employee_name]
                try:
                    await context.bot.send_message(
                        chat_id=emp_chat_id,
                        text=f"📢 Notification for Task #{task_id}:\n"
                             f"Task: {task['task']}\n"
                             f"Message: {notification}"
                    )
                    success_count += 1
                except Exception as e:
                    logger.error(f"Failed to send notification to {employee_name}: {e}")
                    failed_sends.append(employee_name)
        
        # Store notification in task history
        task.setdefault('notifications', []).append({
            'message': notification,
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        
        # Send status to admin
        if failed_sends:
            await update.message.reply_text(
                f"✅ Notification sent to {success_count} employees\n"
                f"❌ Failed to send to: {', '.join(failed_sends)}"
            )
        else:
            await update.message.reply_text(f"✅ Notification sent to all {success_count} employees!")
            
    except Exception as e:
        logger.error(f"Error in notify_command: {e}")
        await update.message.reply_text("❌ An error occurred while sending notification.")

async def handle_media_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle media messages for clarifications, inquiries, and broadcasts."""
    try:
        chat_id = str(update.message.chat_id)
        user_state = context.user_data.get('state', '')
        task_id = context.user_data.get('task_id')
        
        if not user_state:
            await update.message.reply_text("❌ Please use a command first.")
            return

        if user_state == 'awaiting_clarification':
            # Handle clarification from admin
            if chat_id != YOUR_ID:
                await update.message.reply_text("❌ Only admin can send clarifications.")
                return
                
            if not task_id:
                await update.message.reply_text("❌ No task selected. Please use /clarify <task_id> first.")
                return
                
            # Get task details
            task = TASKS.get(task_id)
            if not task:
                await update.message.reply_text("❌ Task not found.")
                context.user_data.clear()
                return
                
            if task['status'] == 'completed':
                await update.message.reply_text("❌ Cannot clarify a completed task.")
                context.user_data.clear()
                return
                
            # Forward media to employee
            employee_id = task['employee_id']
            try:
                # Handle different types of media
                if update.message.text:
                    await context.bot.send_message(
                        chat_id=employee_id,
                        text=f"📝 Clarification for Task #{task_id}:\n{update.message.text}"
                    )
                elif update.message.voice:
                    await context.bot.send_voice(
                        chat_id=employee_id,
                        voice=update.message.voice.file_id,
                        caption=f"🎤 Voice clarification for Task #{task_id}"
                    )
                elif update.message.document:
                    await context.bot.send_document(
                        chat_id=employee_id,
                        document=update.message.document.file_id,
                        caption=f"📎 Document clarification for Task #{task_id}"
                    )
                elif update.message.photo:
                    await context.bot.send_photo(
                        chat_id=employee_id,
                        photo=update.message.photo[-1].file_id,
                        caption=f"🖼 Photo clarification for Task #{task_id}"
                    )
                
                await update.message.reply_text("✅ Clarification sent successfully.")
                
            except Exception as e:
                logger.error(f"Error sending clarification: {e}")
                await update.message.reply_text("❌ Failed to send clarification.")
                
            context.user_data.clear()

        elif user_state == 'awaiting_inquiry':
            # Handle inquiry from employee
            if chat_id == YOUR_ID:
                await update.message.reply_text("❌ Admin cannot send inquiries.")
                return
                
            if not task_id:
                await update.message.reply_text("❌ No task selected. Please use /inquire <task_id> first.")
                return
                
            # Get task details
            task = TASKS.get(task_id)
            if not task:
                await update.message.reply_text("❌ Task not found.")
                context.user_data.clear()
                return
                
            if task['status'] == 'completed':
                await update.message.reply_text("❌ Cannot inquire about a completed task.")
                context.user_data.clear()
                return
                
            if task['employee_id'] != chat_id:
                await update.message.reply_text("❌ This task is not assigned to you.")
                context.user_data.clear()
                return
            
            try:
                # Forward inquiry to admin
                if update.message.text:
                    await context.bot.send_message(
                        chat_id=YOUR_ID,
                        text=f"❓ Inquiry for Task #{task_id}:\n{update.message.text}"
                    )
                elif update.message.voice:
                    await context.bot.send_voice(
                        chat_id=YOUR_ID,
                        voice=update.message.voice.file_id,
                        caption=f"🎤 Voice inquiry for Task #{task_id}"
                    )
                elif update.message.document:
                    await context.bot.send_document(
                        chat_id=YOUR_ID,
                        document=update.message.document.file_id,
                        caption=f"📎 Document inquiry for Task #{task_id}"
                    )
                elif update.message.photo:
                    await context.bot.send_photo(
                        chat_id=YOUR_ID,
                        photo=update.message.photo[-1].file_id,
                        caption=f"🖼 Photo inquiry for Task #{task_id}"
                    )
                
                await update.message.reply_text("✅ Inquiry sent to admin.")
                
            except Exception as e:
                logger.error(f"Error sending inquiry: {e}")
                await update.message.reply_text("❌ Failed to send inquiry.")
                
            context.user_data.clear()

        elif user_state == 'awaiting_broadcast':
            # Handle broadcast from admin
            if chat_id != YOUR_ID:
                await update.message.reply_text("❌ Only admin can broadcast messages.")
                return
            
            success_count = 0
            fail_count = 0
            
            for employee_id in EMPLOYEES.keys():
                try:
                    if update.message.text:
                        await context.bot.send_message(
                            chat_id=employee_id,
                            text=f"📢 Broadcast:\n{update.message.text}"
                        )
                    elif update.message.voice:
                        await context.bot.send_voice(
                            chat_id=employee_id,
                            voice=update.message.voice.file_id,
                            caption="🎤 Voice broadcast"
                        )
                    elif update.message.document:
                        await context.bot.send_document(
                            chat_id=employee_id,
                            document=update.message.document.file_id,
                            caption="📎 Document broadcast"
                        )
                    elif update.message.photo:
                        await context.bot.send_photo(
                            chat_id=employee_id,
                            photo=update.message.photo[-1].file_id,
                            caption="🖼 Photo broadcast"
                        )
                    success_count += 1
                except Exception as e:
                    logger.error(f"Error broadcasting to {employee_id}: {e}")
                    fail_count += 1
            
            status = f"✅ Broadcast sent to {success_count} employees"
            if fail_count > 0:
                status += f"\n❌ Failed to send to {fail_count} employees"
            await update.message.reply_text(status)
            context.user_data.clear()

    except Exception as e:
        logger.error(f"Error in handle_media_message: {e}")
        await update.message.reply_text("❌ An error occurred while processing your message.")
        context.user_data.clear()

async def handle_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks"""
    try:
        query = update.callback_query
        data = query.data
        
        if data.startswith('taskdone_'):
            task_id = int(data.split('_')[1])
            await query.answer()
            await taskdone_command(update, context)
        elif data.startswith('inquire_'):
            task_id = int(data.split('_')[1])
            await query.answer()
            context.user_data['inquiring_task'] = task_id
            await query.message.reply_text(
                f"📝 Send your question about Task #{task_id}\n"
                f"You can send:\n"
                f"• Text message\n"
                f"• Voice message\n"
                f"• Files/documents"
            )
        elif data == 'add_employee':
            await query.answer()
            await query.message.reply_text(
                "To add a new employee, use the format:\n"
                "/add_employee <name> <chat_id>"
            )
            
    except Exception as e:
        logger.error(f"Error in handle_button_callback: {e}")
        await query.answer("❌ An error occurred")

async def taskdone_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /taskdone command for employees"""
    chat_id = str(update.message.chat_id)
    employee_name = get_employee_name(chat_id)
    
    if not employee_name:
        await update.message.reply_text("❌ Only registered employees can use this command!")
        return
    
    try:
        args = context.args
        if not args or not args[0].isdigit():
            await update.message.reply_text(
                "❌ Usage: /taskdone <task_id>"
            )
            return
        
        task_id = int(args[0])
        
        # Get task from database
        task_info = await db.get_task(task_id)
        
        if not task_info:
            await update.message.reply_text(f"❌ Task #{task_id} not found!")
            return
        
        if employee_name not in task_info['employees']:
            await update.message.reply_text("❌ This task is not assigned to you!")
            return
        
        if task_info['status'] != 'active':
            await update.message.reply_text(f"❌ Task #{task_id} is already completed!")
            return
        
        # Mark task as completed in database
        success = await db.update_task_status(task_id, 'completed', employee_name)
        
        if not success:
            await update.message.reply_text(f"❌ Failed to update task status. Please try again.")
            return
        
        # Get updated task for notification
        updated_task = await db.get_task(task_id)
        completed_time = updated_task.get('completed_at', datetime.now()).strftime('%I:%M %p')
        
        # Notify admin
        await context.bot.send_message(
            chat_id=YOUR_ID,
            text=f"✅ Task #{task_id} completed by {employee_name}\n"
                 f"Task: {task_info['task']}\n"
                 f"Completed at: {completed_time} (UAE)"
        )
        
        await update.message.reply_text(f"✅ Task #{task_id} marked as completed!")
        
    except Exception as e:
        logger.error(f"Error in taskdone_command: {e}")
        await update.message.reply_text("❌ Failed to process command. Please try again.")

async def notify_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /notify command for employees"""
    chat_id = str(update.message.chat_id)
    employee_name = get_employee_name(chat_id)
    
    if not employee_name:
        await update.message.reply_text("❌ Only registered employees can use this command!")
        return
    
    # Store context for handling the next message
    context.user_data['notifying'] = True
    
    await update.message.reply_text(
        "📝 Send your notification to admin\n"
        "You can send:\n"
        "• Text message\n"
        "• Voice message\n"
        "• Files/Photos"
    )

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /broadcast command for admin to send custom messages"""
    try:
        chat_id = str(update.message.chat_id)
        if chat_id != YOUR_ID:
            await update.message.reply_text("❌ Only admin can use this command!")
            return
        
        # Store context for handling the next message
        context.user_data['broadcasting'] = True
        
        await update.message.reply_text(
            "📢 Send your broadcast message.\n"
            "You can send:\n"
            "• Text message\n"
            "• Voice message\n"
            "• Files/Documents\n"
            "• Photos"
        )
        
    except Exception as e:
        logger.error(f"Error in broadcast_command: {e}")
        await update.message.reply_text("❌ An error occurred.")

async def mytasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /mytasks command for employees to view their tasks"""
    try:
        chat_id = str(update.message.chat_id)
        employee_name = get_employee_name(chat_id)
        
        if not employee_name:
            await update.message.reply_text("❌ Only registered employees can use this command!")
            return
            
        # Get active tasks for this employee
        employee_tasks = {
            tid: task for tid, task in TASKS.items()
            if employee_name in task['employees'] and task['status'] == 'active'
        }
        
        if not employee_tasks:
            await update.message.reply_text("📝 You have no active tasks at the moment.")
            return
            
        message = "📋 Your Active Tasks:\n\n"
        for task_id, task in employee_tasks.items():
            message += (
                f"Task #{task_id}:\n"
                f"• Description: {task['task']}\n"
                f"• Created: {task['created_at'].strftime('%I:%M %p')} (UAE)\n\n"
            )
            # Add action buttons for each task
            keyboard = [
                [
                    InlineKeyboardButton("✅ Mark Done", callback_data=f"taskdone_{task_id}"),
                    InlineKeyboardButton("❓ Ask Question", callback_data=f"inquire_{task_id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(message, reply_markup=reply_markup)
            message = ""  # Reset for next task
            
    except Exception as e:
        logger.error(f"Error in mytasks_command: {e}")
        await update.message.reply_text("❌ An error occurred while fetching your tasks.")

async def inquire_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /inquire command for employees to ask questions about tasks"""
    try:
        chat_id = str(update.message.chat_id)
        employee_name = None
        
        # Find employee by chat ID
        for name, emp_id in EMPLOYEES.items():
            if emp_id == chat_id:
                employee_name = name
                break
                
        if not employee_name:
            await update.message.reply_text("❌ You are not registered as an employee.")
            return
            
        # If no task ID provided, show active tasks
        if not context.args:
            active_tasks = []
            for task_id, task in TASKS.items():
                if (employee_name in task.get('employees', []) and 
                    task.get('status') != 'completed'):
                    active_tasks.append(f"Task #{task_id}: {task['task']}")
            
            if not active_tasks:
                await update.message.reply_text("📝 You have no active tasks to inquire about.")
                return
                
            message = (
                "To ask a question, use:\n"
                "/inquire <task_id>\n\n"
                "📋 Your Active Tasks:\n\n" + 
                "\n\n".join(active_tasks)
            )
            await update.message.reply_text(message)
            return
            
        task_id = context.args[0]
        
        if task_id not in TASKS:
            await update.message.reply_text("❌ Invalid task ID.")
            return
            
        task = TASKS[task_id]
        
        if employee_name not in task.get('employees', []):
            await update.message.reply_text("❌ You are not assigned to this task.")
            return
            
        if task.get('status') == 'completed':
            await update.message.reply_text("❌ Cannot inquire about completed task.")
            return
            
        # Store context for handling the next message
        context.user_data['inquiring_task'] = {
            'task_id': task_id,
            'employee_name': employee_name
        }
        
        await update.message.reply_text(
            f"📝 Ask your question about Task #{task_id}:\n"
            f"{task['task']}\n\n"
            "You can send:\n"
            "• Text message\n"
            "• Voice message\n"
            "• Files/Documents\n"
            "• Photos"
        )
        
    except Exception as e:
        logger.error(f"Error in inquire_command: {e}")
        await update.message.reply_text("❌ An error occurred while processing your command.")

async def handle_inquiry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inquiry messages from employees"""
    try:
        if 'inquiring_task' not in context.user_data:
            return
            
        inquiry_data = context.user_data['inquiring_task']
        task_id = inquiry_data['task_id']
        employee_name = inquiry_data['employee_name']
        task = TASKS[task_id]
        
        # Handle different types of media
        message_text = update.message.text if update.message.text else None
        voice = update.message.voice.file_id if update.message.voice else None
        document = update.message.document.file_id if update.message.document else None
        photo = update.message.photo[-1].file_id if update.message.photo else None
        
        # Store inquiry in task history
        inquiry = {
            'type': 'text' if message_text else 'voice' if voice else 'document' if document else 'photo',
            'content': message_text or voice or document or photo,
            'employee': employee_name,
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        task.setdefault('inquiries', []).append(inquiry)
        
        # Send to admin
        try:
            # Send header message
            await context.bot.send_message(
                chat_id=YOUR_ID,
                text=f"❓ New inquiry for Task #{task_id}\n"
                     f"From: {employee_name}\n"
                     f"Task: {task['task']}\n\n"
                     f"Question:"
            )
            
            # Send the actual content
            if message_text:
                await context.bot.send_message(chat_id=YOUR_ID, text=message_text)
            elif voice:
                await context.bot.send_voice(chat_id=YOUR_ID, voice=voice)
            elif document:
                await context.bot.send_document(chat_id=YOUR_ID, document=document)
            elif photo:
                await context.bot.send_photo(chat_id=YOUR_ID, photo=photo)
                
            # Send confirmation to employee
            await update.message.reply_text("✅ Your question has been sent to the admin.")
            
        except Exception as e:
            logger.error(f"Failed to send inquiry to admin: {e}")
            await update.message.reply_text("❌ Failed to send your question. Please try again later.")
            
        # Clear context
        del context.user_data['inquiring_task']
        
    except Exception as e:
        logger.error(f"Error in handle_inquiry: {e}")
        await update.message.reply_text("❌ An error occurred while processing your question.")

# Helper function for scheduled messages
async def send_fixed_message(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send fixed message to all employees"""
    try:
        time_of_day = context.job.data['time_of_day']
        message = FIXED_MESSAGES[time_of_day]
        
        # Send to all employees
        for employee_name, chat_id in EMPLOYEES.items():
            try:
                # Check if chat exists
                try:
                    await context.bot.get_chat(chat_id)
                except Exception:
                    logger.warning(f"Chat {chat_id} for {employee_name} not found. Removing from active employees.")
                    del ACTIVE_EMPLOYEES[employee_name]
                    continue

                await context.bot.send_message(
                    chat_id=chat_id,
                    text=message
                )
                logger.info(f"Sent {time_of_day} message to {employee_name}")
            except Exception as e:
                logger.error(f"Failed to send {time_of_day} message to {employee_name}: {e}")
                
    except Exception as e:
        logger.error(f"Error in send_fixed_message: {e}")

async def send_task_reminder(context: ContextTypes.DEFAULT_TYPE):
    """Send reminder for specific task"""
    job = context.job
    task_id = job.data['task_id']
    
    try:
        # Get task from database
        task_info = await db.get_task(task_id)
        
        if task_info and task_info['status'] == 'active':
            message = (
                f"⏰ Reminder: Task #{task_id}\n\n"
                f"Task: {task_info['task']}\n"
                f"Use /taskdone {task_id} when completed"
            )
            
            for employee in task_info['employees']:
                try:
                    await context.bot.send_message(
                        chat_id=EMPLOYEES[employee],
                        text=message
                    )
                except Exception as e:
                    logger.error(f"Failed to send reminder to {employee}: {e}")
        else:
            logger.info(f"Task #{task_id} is no longer active, removing reminder job")
            job.schedule_removal()
    except Exception as e:
        logger.error(f"Error in send_task_reminder for task #{task_id}: {e}")

async def log_all_updates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log all incoming updates for debugging purposes"""
    try:
        logger.info(f"Received update with ID: {update.update_id}")
        
        if update.message:
            logger.info(f"MESSAGE: {update.message.text} from user {update.message.from_user.id} ({update.message.from_user.username})")
            
            # Check if it's a command and log it specially
            if update.message.text and update.message.text.startswith('/'):
                logger.info(f"COMMAND DETECTED: {update.message.text}")
                
                # Extract command name and arguments
                command_parts = update.message.text.split()
                command = command_parts[0].lower()
                args = command_parts[1:] if len(command_parts) > 1 else []
                
                logger.info(f"Command: {command}, Args: {args}")
                
        elif update.callback_query:
            logger.info(f"CALLBACK: {update.callback_query.data} from user {update.callback_query.from_user.id}")
        elif update.edited_message:
            logger.info(f"EDITED: {update.edited_message.text} from user {update.edited_message.from_user.id}")
        else:
            logger.info(f"OTHER UPDATE TYPE: {update}")
            
    except Exception as e:
        logger.error(f"Error in log_all_updates: {e}")
        logger.error(f"Update object: {update}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors in the telegram bot."""
    logger.error(f"Exception while handling an update: {context.error}")
    
    try:
        # Send error message to admin
        error_message = f"⚠️ Bot Error: {context.error}\n\nUpdate: {update}"
        
        # Truncate message if it's too long
        if len(error_message) > 4000:
            error_message = error_message[:4000] + "..."
            
        await context.bot.send_message(
            chat_id=YOUR_ID,
            text=error_message
        )
    except Exception as e:
        logger.error(f"Failed to send error notification: {e}")

async def ping():
    """Self-ping to keep the service alive"""
    try:
        # Get the service URL from environment or use a default
        service_url = os.getenv('SERVICE_URL', 'https://trichygold-bot-db.onrender.com')
        ping_url = f"{service_url}/ping"
        
        async with aiohttp.ClientSession() as session:
            while True:
                try:
                    async with session.get(ping_url) as response:
                        if response.status != 200:
                            logger.warning(f"Ping failed with status {response.status}")
                    await asyncio.sleep(60)  # Wait for 1 minute before next ping
                except Exception as e:
                    logger.error(f"Error in ping: {e}")
                    await asyncio.sleep(60)  # Still wait even if there's an error

    except Exception as e:
        logger.error(f"Fatal error in ping: {e}")

@app.route('/')
async def health_check():
    return "Bot is running", 200

async def db_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /dbstatus command to check MongoDB connection status"""
    chat_id = update.message.chat_id
    user_id = str(chat_id)
    
    # Allow all users to check basic database status
    # But show more details to admin
    is_admin = user_id == YOUR_ID
    
    # Log the command for debugging
    logger.info(f"DB status command received from user {user_id} (admin: {is_admin})")
    
    # Check MongoDB connection status
    is_connected = db.is_connected()
    connection_details = db.get_connection_details()
    
    if is_connected:
        # Get more detailed information
        try:
            server_info = connection_details.get("server_info", {})
            connections_info = server_info.get("connections", {})
            active_connections = connections_info.get("current", "unknown")
            available_connections = connections_info.get("available", "unknown")
            
            message = (
                f"✅ MongoDB Connection Status: CONNECTED\n\n"
                f"Server: {server_info.get('host', 'unknown')}\n"
                f"Version: {server_info.get('version', 'unknown')}\n"
                f"Database: {db.db.name}\n"
                f"Active Connections: {active_connections}\n"
                f"Available Connections: {available_connections}\n"
                f"Last Connection Attempt: {connection_details.get('last_attempt', 'unknown')}\n\n"
                f"Storage Mode: MongoDB\n\n"
                f"Commands:\n"
                f"/dbreconnect - Force reconnection attempt\n"
                f"/dbmigrate - Migrate in-memory data to MongoDB"
            )
        except Exception as e:
            message = (
                f"✅ MongoDB Connection Status: CONNECTED\n\n"
                f"Could not retrieve detailed info: {str(e)}\n\n"
                f"Storage Mode: MongoDB\n\n"
                f"Commands:\n"
                f"/dbreconnect - Force reconnection attempt\n"
                f"/dbmigrate - Migrate in-memory data to MongoDB"
            )
    else:
        # Get error information
        error_msg = connection_details.get("error", "Unknown error")
        last_attempt = connection_details.get("last_attempt", "Never")
        reconnect_attempts = connection_details.get("reconnect_attempts", 0)
        
        message = (
            f"❌ MongoDB Connection Status: DISCONNECTED\n\n"
            f"Error: {error_msg}\n"
            f"Last Connection Attempt: {last_attempt}\n"
            f"Reconnection Attempts: {reconnect_attempts}\n\n"
            f"Using fallback in-memory storage.\n"
            f"Note: Data will be lost when the bot restarts.\n\n"
            f"Storage Mode: In-Memory\n\n"
            f"Commands:\n"
            f"/dbreconnect - Force reconnection attempt"
        )
    
    await context.bot.send_message(
        chat_id=chat_id,
        text=message
    )

async def db_reconnect_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /dbreconnect command to force a reconnection attempt to MongoDB"""
    chat_id = update.message.chat_id
    user_id = str(chat_id)
    
    # Only allow admin to force reconnection
    if user_id != YOUR_ID:
        await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ Sorry, only admin can force database reconnection."
        )
        return
    
    # Send initial message
    status_message = await context.bot.send_message(
        chat_id=chat_id,
        text="🔄 Attempting to reconnect to MongoDB..."
    )
    
    # Force reconnection attempt
    reconnection_successful = await db.try_reconnect()
    
    if reconnection_successful:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_message.message_id,
            text="✅ Successfully reconnected to MongoDB!\n\nUse /dbstatus to see connection details."
        )
        
        # Check if we need to migrate in-memory data
        if db.in_memory_mode:
            await context.bot.send_message(
                chat_id=chat_id,
                text="ℹ️ You have data in memory that can be migrated to MongoDB.\n\nUse /dbmigrate to transfer this data."
            )
    else:
        connection_details = db.get_connection_details()
        error_msg = connection_details.get("error", "Unknown error")
        
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_message.message_id,
            text=f"❌ Failed to reconnect to MongoDB.\n\nError: {error_msg}\n\nUse /dbstatus to see connection details."
        )

async def db_migrate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /dbmigrate command to migrate in-memory data to MongoDB"""
    chat_id = update.message.chat_id
    user_id = str(chat_id)
    
    # Only allow admin to migrate data
    if user_id != YOUR_ID:
        await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ Sorry, only admin can migrate database data."
        )
        return
    
    # Check if migration is needed
    if not db.in_memory_mode:
        await context.bot.send_message(
            chat_id=chat_id,
            text="ℹ️ No migration needed. Already using MongoDB for storage."
        )
        return
    
    # Check if MongoDB is connected
    if not db.is_connected():
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ Cannot migrate data. MongoDB is not connected.\n\nUse /dbreconnect to try reconnecting first."
        )
        return
    
    # Send initial message
    status_message = await context.bot.send_message(
        chat_id=chat_id,
        text="🔄 Migrating in-memory data to MongoDB..."
    )
    
    # Perform migration
    success, migrated_count = await db.migrate_memory_to_db()
    
    if success:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_message.message_id,
            text=f"✅ Successfully migrated {migrated_count} items to MongoDB!\n\nStorage mode switched to MongoDB.\n\nUse /dbstatus to see connection details."
        )
    else:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_message.message_id,
            text=f"❌ Failed to migrate data to MongoDB.\n\nStill using in-memory storage.\n\nUse /dbstatus to see connection details."
        )


@app.route('/webhook', methods=['POST'])
async def webhook():
    data = await request.get_json()
    update = Update.de_json(data, application.bot)
    if update:
        await application.process_update(update)
    return "OK", 200

async def main() -> None:
    """Start the bot."""
    try:
        # Use the global application instance instead of creating a new one
        global application

        # Command handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("assign", assign_task))
        application.add_handler(CommandHandler("done", done_command))
        application.add_handler(CommandHandler("clarify", clarify_command))
        application.add_handler(CommandHandler("inquire", inquire_command))
        application.add_handler(CommandHandler("taskdone", taskdone_command))
        application.add_handler(CommandHandler("notify", notify_command))
        application.add_handler(CommandHandler("broadcast", broadcast_command))
        application.add_handler(CommandHandler("list_employees", list_employees_command))
        application.add_handler(CommandHandler("mytasks", mytasks_command))
        application.add_handler(CommandHandler("dbstatus", db_status_command))
        application.add_handler(CommandHandler("dbreconnect", db_reconnect_command))
        application.add_handler(CommandHandler("dbmigrate", db_migrate_command))
        
        # Media message handler for clarifications, inquiries, and broadcasts
        application.add_handler(MessageHandler(
            filters.TEXT | filters.VOICE | filters.Document.ALL | filters.PHOTO,
            handle_media_message
        ))
        
        # Callback query handler for buttons
        application.add_handler(CallbackQueryHandler(handle_button_callback))

        # Add error handler
        application.add_error_handler(error_handler)

        # Configure webhook
        service_url = os.getenv('SERVICE_URL', os.getenv('RENDER_SERVICE_URL'))
        if service_url and not service_url.startswith('http'):
            service_url = f"https://{service_url}"
            
        # Get port from environment variable or use default for Render
        port = int(os.getenv('PORT', 10000))
        logger.info(f"Will bind to port {port}")
        
        # Always start a web server to satisfy Render's port binding requirement
        config = uvicorn.Config(
            app=app,
            host="0.0.0.0",
            port=port,
            loop="asyncio"
        )
        server = uvicorn.Server(config)
        
        # Always use webhook mode on Render or when port 10000 is used (Render's default)
        # Check multiple environment variables that might indicate we're on Render
        is_render = os.environ.get('RENDER') or \
                   os.environ.get('RENDER_SERVICE_ID') or \
                   os.environ.get('RENDER_EXTERNAL_URL') or \
                   port == 10000
            
        if is_render:
            # We're on Render, use webhook mode
            logger.info("Render deployment detected. Using webhook mode.")
            service_url = os.environ.get('RENDER_EXTERNAL_URL')
            if not service_url:
                service_url = f"https://{os.environ.get('RENDER_SERVICE_NAME') or 'your-app'}.onrender.com"
                
            # Set up webhook
            webhook_url = f"{service_url}/webhook"
            logger.info(f"Running on Render. Setting webhook to: {webhook_url}")
            
            # Set up detailed logging for updates
            application.add_handler(MessageHandler(filters.ALL, log_all_updates), group=999)
            
            # Initialize the application
            await application.initialize()
            
            # Set the webhook
            await application.bot.set_webhook(webhook_url)
            
            # Start the webhook server
            logger.info(f"Starting webhook server on port {port}")
            await server.serve()
        else:
            # Local development - polling mode
            logger.info("Local development detected. Running in polling mode.")
            await application.bot.delete_webhook()
            
            # Start the web server in a separate task
            web_server_task = asyncio.create_task(server.serve())
            
            # Set up detailed logging for updates
            application.add_handler(MessageHandler(filters.ALL, log_all_updates), group=999)
            
            # Initialize the application
            await application.initialize()
            
            # Use the Application's run_polling method directly
            logger.info("Starting polling with drop_pending_updates=True")
            await application.run_polling(drop_pending_updates=True)
            
            # This line will only be reached when polling is stopped
            logger.info("Polling has stopped")
    except Exception as e:
        logger.error(f"Fatal error in main: {e}")
        raise

if __name__ == '__main__':
    asyncio.run(main())