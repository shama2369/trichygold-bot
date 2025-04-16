import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
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
import re
import copy

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Get environment variables directly from Render deployment
# No dotenv dependency needed

# Get and log the bot token (without showing the full token for security)
BOT_TOKEN = os.getenv('BOT_TOKEN', '')
if not BOT_TOKEN:
    logger.error("BOT_TOKEN environment variable not set!")
    logger.error("Make sure to set the BOT_TOKEN environment variable in Render dashboard")
    
token_preview = BOT_TOKEN[:10] + '...' if BOT_TOKEN and len(BOT_TOKEN) > 10 else 'Not set'
logger.info(f"Using bot token: {token_preview}")

# Set YOUR_ID to a default value that matches your Telegram ID
YOUR_ID = os.getenv('ADMIN_ID', '1341853859')  # Default to shameem's ID
logger.info(f"Admin ID set to: {YOUR_ID}")

# Initialize database and bot
from database import db
# Import employee handlers
from employee_handlers import add_employee_command, remove_employee_command, list_employees_command
# Import test employees handlers
from test_employees import add_test_employees_command
# Import button handlers
from button_handlers import handle_button_callback
application = Application.builder().token(BOT_TOKEN).build()
app = Quart(__name__)

# Store the admin ID in bot_data for access in handlers
application.bot_data['ADMIN_ID'] = YOUR_ID

# Command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    chat_id = str(update.message.chat_id)
    user = update.message.from_user
    logger.info(f"Start command received from user {user.id} ({user.username})")
    
    # Send an immediate response to prevent other bots from intercepting
    await update.message.reply_text("🔄 Starting TrichyGold Task Manager...")
    
    # Different welcome message for admin vs employees
    if chat_id == YOUR_ID:
        message = f"👋 Welcome to TrichyGold Task Manager, Admin!"
        
        # Create keyboard with admin options
        keyboard = [
            [InlineKeyboardButton("📋 List Employees", callback_data="cmd_list_employees")],
            [InlineKeyboardButton("📝 Assign Task", callback_data="cmd_assign")],
            [InlineKeyboardButton("📊 View Tasks", callback_data="cmd_tasks")],
            [InlineKeyboardButton("❓ Help", callback_data="cmd_help")]
        ]
    else:
        # Check if this is a registered employee
        employee_name = None
        if db.is_connected():
            employee = db.employees.find_one({"chat_id": chat_id})
            if employee:
                employee_name = employee.get("name")
        
        if employee_name:
            message = f"👋 Welcome back, {employee_name}!"
            
            # Create keyboard with employee options
            keyboard = [
                [InlineKeyboardButton("📊 My Tasks", callback_data="cmd_mytasks")],
                [InlineKeyboardButton("❓ Ask Question", callback_data="cmd_inquire")],
                [InlineKeyboardButton("📢 Notify Admin", callback_data="cmd_notify")],
                [InlineKeyboardButton("❓ Help", callback_data="cmd_help")]
            ]
        else:
            message = "👋 Welcome to TrichyGold Task Manager!"
            message += "\n\n⚠️ You are not registered as an employee. Please contact the administrator."
            
            # Simple keyboard for non-registered users
            keyboard = [
                [InlineKeyboardButton("❓ Help", callback_data="cmd_help")]
            ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(message, reply_markup=reply_markup)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /help is issued."""
    chat_id = str(update.message.chat_id)
    
    # Different help message for admin vs employees
    if chat_id == YOUR_ID:
        help_text = (
            "🔑 *Admin Commands*\n\n"
            "/assign \- Assign tasks to employees\n"
            "Format: /assign employee1,employee2 task \[time\]\n\n"
            "/tasks \- View and manage all active tasks\n"
            "Format: /tasks \[task\_id\]\n\n"
            "/clarify \- Add details to tasks\n"
            "Format: /clarify task\_id details\n\n"
            "/broadcast \- Send message to all employees\n"
            "Format: /broadcast message\n\n"
            "/list\_employees \- View all registered employees\n\n"
            "/add\_employee \- Add a new employee\n"
            "Format: /add\_employee name chat\_id\n\n"
            "/remove\_employee \- Remove an employee\n"
            "Format: /remove\_employee chat\_id\n\n"
            "/task \- View tasks assigned to a specific employee\n"
            "Format: /task employee\_name\n\n"
            "/dbstatus \- Check database connection status\n\n"
            "/help \- Show this message\n\n"
            "*Legacy Commands* \(use /tasks instead\):\n"
            "/done \- Same as /tasks\n"
        )
        
        # Create keyboard with admin quick actions
        keyboard = [
            [InlineKeyboardButton("📋 List Employees", callback_data="cmd_list_employees")],
            [InlineKeyboardButton("📝 Assign Task", callback_data="cmd_assign")],
            [InlineKeyboardButton("📊 View Tasks", callback_data="cmd_tasks")]
        ]
    else:
        help_text = (
            "👤 *Employee Commands*\n\n"
            "/tasks \- View your tasks and mark them as completed\n"
            "Format: /tasks \[task\_id\]\n\n"
            "/inquire \- Ask questions about tasks\n"
            "Format: /inquire task\_id question\n\n"
            "/notify \- Send notice to admin\n"
            "Format: /notify message\n\n"
            "/help \- Show this message\n\n"
            "*Legacy Commands* \(use /tasks instead\):\n"
            "/taskdone \- Same as /tasks\n"
            "/mytasks \- Same as /tasks\n"
        )
        
        # Create keyboard with employee quick actions
        keyboard = [
            [InlineKeyboardButton("📊 My Tasks", callback_data="cmd_mytasks")],
            [InlineKeyboardButton("❓ Ask Question", callback_data="cmd_inquire")],
            [InlineKeyboardButton("📢 Notify Admin", callback_data="cmd_notify")]
        ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(help_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

# Initialize employees directly in MongoDB
def initialize_employees_in_mongodb():
    try:
        # Check if we have a connection to MongoDB
        if not db.is_connected():
            logger.warning("Cannot initialize employees: MongoDB not connected")
            return
            
        # Make sure we have the employees collection
        if not hasattr(db, 'employees') or db.employees is None:
            db.employees = db.db.employees
            
        # Default employees to add if none exist
        default_employees = [
            {'name': 'shameem', 'chat_id': '1341853859'},
            {'name': 'rehan', 'chat_id': '1475715464'}
        ]
        
        # Check if we already have employees in MongoDB
        existing_count = db.employees.count_documents({})
        
        if existing_count == 0:
            # Add default employees to MongoDB
            for employee in default_employees:
                db.employees.update_one(
                    {'chat_id': employee['chat_id']},
                    {'$set': employee},
                    upsert=True
                )
            logger.info(f"Added {len(default_employees)} default employees to MongoDB")
        else:
            logger.info(f"Found {existing_count} existing employees in MongoDB")
    except Exception as e:
        logger.error(f"Error initializing employees in MongoDB: {e}")

# Run the initialization
initialize_employees_in_mongodb()

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
    """Get employee name from MongoDB by chat_id"""
    try:
        # Ensure we have a connection to MongoDB
        if not db.is_connected():
            logger.warning("Cannot get employee name: MongoDB not connected")
            return None
            
        # Make sure we have the employees collection
        if not hasattr(db, 'employees') or db.employees is None:
            db.employees = db.db.employees
            
        # Find employee by chat_id
        employee = db.employees.find_one({'chat_id': str(chat_id)})
        
        if employee and 'name' in employee:
            return employee['name']
            
        return None
    except Exception as e:
        logger.error(f"Error getting employee name: {e}")
        return None

def format_task_message(task, minutes, priority=None, due_date=None, assigned_date=None):
    """Format a task message with proper time display, priority, and due date"""
    # Format reminder interval in a user-friendly way
    if minutes < 60:
        reminder_text = f"Every {minutes} minutes"
    elif minutes < 60 * 24:
        hours = minutes / 60
        if hours == 1:
            reminder_text = "Every hour"
        else:
            reminder_text = f"Every {int(hours)} hours"
    else:
        days = minutes / (60 * 24)
        if days == 1:
            reminder_text = "Every day"
        else:
            reminder_text = f"Every {int(days)} days"
    
    # Create priority icon if priority is specified
    priority_text = ""
    if priority:
        priority_icon = "🔴" if priority.lower() == "high" else "🟡" if priority.lower() == "medium" else "🟢"
        priority_text = f"*Priority:* {priority_icon} {priority.capitalize()}\n"
    
    # Add due date if specified
    due_date_text = ""
    if due_date:
        due_date_text = f"*Due Date:* {due_date}\n"
    
    # Add assigned date - use current time as fallback
    if not assigned_date:
        assigned_date = datetime.now().strftime('%Y-%m-%d %H:%M')
    assigned_date_text = f"*Assigned:* {assigned_date}\n"
    
    # Format the message with Markdown
    return (
        f"📋 *New Task Assigned!*\n\n"
        f"*Task:* {task}\n"
        f"{priority_text}"
        f"{due_date_text}"
        f"{assigned_date_text}"
        f"*Reminder:* {reminder_text}\n\n"
        f"Mark as done when completed."
    )

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
        # Admin welcome message
        welcome_message = (
            f"👋 Welcome to TrichyGold Task Manager!\n\n"
            f"🔑 You are logged in as ADMIN\n"
            f"Your Chat ID: {chat_id}\n\n"
            f"Select a command below:"
        )
        
        # Create buttons for admin commands
        keyboard = [
            [InlineKeyboardButton("📝 Assign Tasks", callback_data="cmd_assign"),
             InlineKeyboardButton("📃 View Tasks", callback_data="cmd_tasks")],
            [InlineKeyboardButton("💬 Clarify Tasks", callback_data="cmd_clarify"),
             InlineKeyboardButton("📢 Broadcast", callback_data="cmd_broadcast")],
            [InlineKeyboardButton("👤 List Employees", callback_data="cmd_list_employees"),
             InlineKeyboardButton("❓ Help", callback_data="cmd_help")]
        ]
    else:
        employee_name = get_employee_name(chat_id)
        if employee_name:
            # Employee welcome message
            welcome_message = (
                f"👋 Welcome {user_name}!\n\n"
                f"You are registered as: {employee_name}\n"
                f"Your Chat ID: {chat_id}\n\n"
                f"Select a command below:"
            )
            
            # Create buttons for employee commands - simplified menu
            keyboard = [
                [InlineKeyboardButton("📄 View Tasks", callback_data="cmd_tasks"),
                 InlineKeyboardButton("❓ Ask Questions", callback_data="cmd_inquire")],
                [InlineKeyboardButton("📢 Notify Admin", callback_data="cmd_notify"),
                 InlineKeyboardButton("❓ Help", callback_data="cmd_help")]
            ]
        else:
            # Unregistered user welcome message
            welcome_message = (
                f"👋 Welcome {user_name}!\n\n"
                f"⚠️ You are not registered.\n"
                f"Your Chat ID: {chat_id}\n\n"
                f"Please contact admin to get registered."
            )
            # No buttons for unregistered users
            keyboard = []
    
    # Create reply markup if there are buttons
    if keyboard:
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(welcome_message, reply_markup=reply_markup)
    else:
        await update.message.reply_text(welcome_message)

async def assign_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /assign command for task assignment"""
    # Import datetime at the function level to avoid scope issues
    from datetime import datetime, timedelta
    
    logger.info(f"assign_task called with update: {update.message.text}")
    logger.info(f"User ID: {update.message.chat_id}, Admin ID: {YOUR_ID}")
    
    if str(update.message.chat_id) != YOUR_ID:
        logger.warning(f"Unauthorized access attempt from {update.message.chat_id}")
        await update.message.reply_text("❌ Only admin can assign tasks!")
        return
    
    try:
        logger.info(f"Context args: {context.args}")
        args = context.args
        if len(args) < 2:
            logger.warning(f"Insufficient arguments: {args}")
            await update.message.reply_text(
                "❌ *Task Assignment Command Format*\n\n"
                "`/assign employee1,employee2 <task> [time] [p:priority] [due:date]`\n\n"
                "*Required Parameters:*\n"
                "• `employee1,employee2` - Comma-separated list of employees\n"
                "• `<task>` - Task description\n\n"
                "*Optional Parameters:*\n\n"
                "*Time Format:*\n"
                "• `30m` - 30 minutes\n"
                "• `2h` - 2 hours\n"
                "• `1d` - 1 day\n\n"
                "*Priority Options:*\n"
                "• `p:high` - 🔴 High priority\n"
                "• `p:medium` - 🟡 Medium priority\n"
                "• `p:low` - 🟢 Low priority\n\n"
                "*Due Date Options:*\n"
                "• `due:today` - Due today\n"
                "• `due:tomorrow` - Due tomorrow\n"
                "• `due:nextweek` - Due next week\n"
                "• `due:YYYY-MM-DD` - Due on specific date\n\n"
                "*Examples:*\n"
                "`/assign rehan,shameem Check inventory 30m p:high due:tomorrow`\n"
                "`/assign rehan Daily report 1d p:medium due:2025-04-20`",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Parse employees
        employee_names = [emp.strip() for emp in args[0].split(',')]
        
        # Check if database is connected
        if not db.is_connected():
            await update.message.reply_text("❌ Database connection error. Please try again later.")
            return
            
        # Get all employees from database
        all_employees = list(db.employees.find())
        available_employees = {emp['name'].lower(): emp['chat_id'] for emp in all_employees}
        
        # Check for invalid employee names
        invalid_employees = [emp for emp in employee_names if emp.lower() not in available_employees]
        if invalid_employees:
            await update.message.reply_text(
                f"❌ Unknown employees: {', '.join(invalid_employees)}\n"
                f"Available: {', '.join(available_employees.keys())}"
            )
            return
            
        # Get chat IDs for the valid employees
        employee_chat_ids = [available_employees[emp.lower()] for emp in employee_names]
        
        # Parse task and time units
        task_parts = args[1:]
        minutes = 60  # default reminder interval (60 minutes)
        priority = None
        due_date = None
        filtered_parts = []
        
        # Scan all parts for time units, priority, and due date flags
        for part in task_parts:
            # Check for time unit patterns like 30m, 2h, 1d
            time_match = re.match(r'^(\d+)([mhd])$', part.lower())
            if time_match:
                value, unit = time_match.groups()
                value = int(value)
                
                if unit == 'm':  # minutes
                    minutes = value
                elif unit == 'h':  # hours
                    minutes = value * 60
                elif unit == 'd':  # days
                    minutes = value * 60 * 24
                continue  # Skip adding this to filtered_parts
                
            # Check if it's just a number (assume minutes)
            elif part.isdigit():
                minutes = int(part)
                continue  # Skip adding this to filtered_parts
                
            # Check for priority flag (p:high, p:medium, p:low)
            elif part.lower().startswith('p:'):
                priority_value = part[2:].lower()
                if priority_value in ['high', 'medium', 'low']:
                    priority = priority_value
                    continue  # Skip adding this to filtered_parts
            
            # Check for due date flag (due:tomorrow, due:2025-04-20, etc.)
            elif part.lower().startswith('due:'):
                date_value = part[4:].lower()
                
                # Handle special keywords
                if date_value == 'tomorrow':
                    tomorrow = datetime.now() + timedelta(days=1)
                    due_date = tomorrow.strftime('%Y-%m-%d')
                elif date_value == 'today':
                    due_date = datetime.now().strftime('%Y-%m-%d')
                elif date_value == 'nextweek':
                    next_week = datetime.now() + timedelta(days=7)
                    due_date = next_week.strftime('%Y-%m-%d')
                else:
                    # Assume it's a date string
                    due_date = date_value
                continue  # Skip adding this to filtered_parts
            
            # If not a special flag, keep it as part of the task description
            filtered_parts.append(part)
        
        # Join the remaining parts as the task description
        task = ' '.join(filtered_parts)
        
        # Get the next task ID from the database
        highest_task = db.tasks.find_one(sort=[('task_id', -1)])
        task_id = 1 if not highest_task else highest_task['task_id'] + 1
        
        # Create task data
        assigned_date = datetime.now()
        formatted_assigned_date = assigned_date.strftime('%Y-%m-%d %H:%M')
        
        task_data = {
            'task_id': task_id,
            'task': task,
            'assigned_by': 'Admin',
            'assigned_to': employee_chat_ids,
            'employees': employee_names,  # Store employee names for easier querying
            'assigned_at': assigned_date,
            'assigned_date': formatted_assigned_date,  # Store formatted date for display
            'reminder_interval': minutes,
            'priority': priority,  # Add priority field
            'due_date': due_date,  # Add due date field
            'status': 'active',
            'completed': False
        }
        
        # Store in database
        db.tasks.insert_one(task_data)
        
        # Send task to each employee
        for i, emp_name in enumerate(employee_names):
            emp_chat_id = employee_chat_ids[i]
            try:
                # Format the task message with priority, due date, and assigned date
                task_message = format_task_message(task, minutes, priority, due_date, formatted_assigned_date)
                
                # Create keyboard with done button
                keyboard = [
                    [InlineKeyboardButton("✅ Mark as Done", callback_data=f"taskdone_{task_id}")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await context.bot.send_message(
                    chat_id=emp_chat_id,
                    text=task_message,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )
                
                logger.info(f"Task {task_id} sent to {emp_name} ({emp_chat_id})")
            except Exception as e:
                logger.error(f"Failed to send task to {emp_name}: {e}")
                await update.message.reply_text(f"❌ Failed to send task to {emp_name}: {str(e)}")
        
        # Format reminder text for admin confirmation message
        if minutes < 60:
            reminder_text = f"Every {minutes} minutes"
        elif minutes < 60 * 24:
            hours = minutes / 60
            if hours == 1:
                reminder_text = "Every hour"
            else:
                reminder_text = f"Every {int(hours)} hours"
        else:
            days = minutes / (60 * 24)
            if days == 1:
                reminder_text = "Every day"
            else:
                reminder_text = f"Every {int(days)} days"
        
        # Create buttons for admin task management
        admin_keyboard = [
            [InlineKeyboardButton("❓ Ask Question", callback_data=f"inquire_{task_id}"),
             InlineKeyboardButton("🗑️ Delete Task", callback_data=f"delete_task_{task_id}")]
        ]
        admin_reply_markup = InlineKeyboardMarkup(admin_keyboard)
        
        # Format priority text for admin confirmation
        priority_text = ""
        if priority:
            priority_icon = "🔴" if priority.lower() == "high" else "🟡" if priority.lower() == "medium" else "🟢"
            priority_text = f"Priority: {priority_icon} {priority.capitalize()}\n"
        
        # Format due date text for admin confirmation
        due_date_text = ""
        if due_date:
            due_date_text = f"Due Date: {due_date}\n"
        
        # Send confirmation to admin
        await update.message.reply_text(
            f"✅ Task #{task_id} assigned to: {', '.join(employee_names)}\n"
            f"Task: {task}\n"
            f"{priority_text}"
            f"{due_date_text}"
            f"Reminders: {reminder_text}",
            reply_markup=admin_reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Schedule reminder
        if context.job_queue:
            logger.info(f"Scheduling reminder for Task #{task_id} every {minutes} minutes")
            context.job_queue.run_repeating(
                send_task_reminder,
                interval=minutes * 60,
                first=minutes * 60,
                data={'task_id': task_id}
            )
    
    except Exception as e:
        import traceback
        logger.error(f"Error in assign_task: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        await update.message.reply_text(f"❌ Failed to assign task: {e}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command to display available commands"""
    chat_id = str(update.message.chat_id)
    
    if chat_id == YOUR_ID:
        # Admin help text - consistent with button help
        help_text = (
            "📐 *TrichyGold Task Manager Help*\n\n"
            "*Admin Commands:*\n"
            "`/assign` - Assign tasks to employees\n"
            "`/tasks` - View and manage all tasks\n"
            "`/clarify` - Add details to a task\n"
            "`/broadcast` - Send message to all employees\n"
            "`/list_employees` - View all employees\n"
            "`/add_employee` - Add a new employee\n"
            "`/remove_employee` - Remove an employee\n"
        )
    else:
        # Employee help text - consistent with button help
        help_text = (
            "📋 Employee Commands\n\n"
            "`/tasks` - View your tasks and mark them as completed\n"
            "`/notify` - Send message to admin\n\n"
            "You can also use the buttons in the main menu to access these features."
        )
    
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

async def send_active_tasks(chat_id, context):
    """Helper function to send active tasks with buttons"""
    try:
        # Get active tasks directly from MongoDB collection
        active_tasks = list(db.tasks.find({"status": {"$ne": "completed"}, "completed": {"$ne": True}}))
        logger.info(f"Using MongoDB: {len(active_tasks)} active tasks found")
        
        if not active_tasks:
            await context.bot.send_message(chat_id=chat_id, text="📝 *No active tasks at the moment.*", parse_mode=ParseMode.MARKDOWN)
            return
            
        # Format tasks based on user role
        if str(chat_id) == YOUR_ID:  # Admin view
            # Create a button for each task for the admin
            for task in active_tasks:
                task_id = task['task_id']
                # Get assigned employee names
                assigned_ids = task.get('assigned_to', [])
                assignees = []
                for emp_id in assigned_ids:
                    emp = db.employees.find_one({"chat_id": str(emp_id)})
                    if emp and emp.get('name'):
                        assignees.append(emp.get('name'))
                
                task_desc = task.get('task', 'No description')
                
                # Format the task information with safe access to fields
                task_message = (
                    f"*Task #{task_id}*\n"
                    f"• *Description:* {task_desc}\n"
                )
                
                # Only add assignees if we have any
                if assignees:
                    task_message += f"• *Assigned to:* {', '.join(assignees)}\n"
                
                # Add time allocation
                task_message += f"• *Time allocated:* {task.get('reminder_interval', 'Not specified')} minutes\n"
                
                # Add assigned date/time if available
                assigned_date = task.get('assigned_date')
                if assigned_date:
                    task_message += f"• *Assigned:* {assigned_date}\n"
                
                # Add due date if available
                due_date = task.get('due_date')
                if due_date:
                    task_message += f"• *Due:* {due_date}\n"
                    
                # Add priority if available
                priority = task.get('priority')
                if priority:
                    priority_icon = "🔴" if priority.lower() == "high" else "🟡" if priority.lower() == "medium" else "🟢"
                    task_message += f"• *Priority:* {priority_icon} {priority}\n"
                
                # Create buttons for task actions
                keyboard = [
                    [InlineKeyboardButton("✅ Mark as Done", callback_data=f"taskdone_{task_id}"),
                     InlineKeyboardButton("❓ Ask Question", callback_data=f"inquire_{task_id}")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                # Send each task as a separate message with buttons
                await context.bot.send_message(chat_id=chat_id, text=task_message, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        else:  # Employee view
            employee_name = get_employee_name(str(chat_id))
            if not employee_name:
                await context.bot.send_message(chat_id=chat_id, text="❌ *You are not registered as an employee.*", parse_mode=ParseMode.MARKDOWN)
                return
                
            # Filter tasks for this employee - check both assigned_to and employees fields
            employee_tasks = []
            for task in active_tasks:
                # Check assigned_to field (contains chat_ids)
                assigned_to = task.get('assigned_to', [])
                # Convert all values to strings for comparison
                assigned_to_str = [str(cid) for cid in assigned_to] if isinstance(assigned_to, list) else []
                
                # Check employees field (contains names)
                employees = task.get('employees', [])
                employees_list = employees if isinstance(employees, list) else []
                
                # Add task if either the chat_id is in assigned_to or employee name is in employees
                if str(chat_id) in assigned_to_str or employee_name in employees_list:
                    employee_tasks.append(task)
            
            if not employee_tasks:
                await context.bot.send_message(chat_id=chat_id, text="📝 *You have no active tasks at the moment.*", parse_mode=ParseMode.MARKDOWN)
                return
                
            # Send each employee task as a separate message with buttons
            for task in employee_tasks:
                task_id = task['task_id']
                # Safely access task fields with defaults
                task_desc = task.get('task', 'No description')
                time_allocated = task.get('reminder_interval', 'Not specified')
                
                # Format the task information with the same styling as admin view
                task_message = (
                    f"*Task #{task_id}*\n"
                    f"• *Description:* {task_desc}\n"
                    f"• *Time allocated:* {time_allocated} minutes\n"
                )
                
                # Add assigned date/time if available
                assigned_date = task.get('assigned_date')
                if assigned_date:
                    task_message += f"• *Assigned:* {assigned_date}\n"
                
                # Add due date if available
                due_date = task.get('due_date')
                if due_date:
                    task_message += f"• *Due:* {due_date}\n"
                    
                # Add priority if available
                priority = task.get('priority')
                if priority:
                    priority_icon = "🔴" if priority.lower() == "high" else "🟡" if priority.lower() == "medium" else "🟢"
                    task_message += f"• *Priority:* {priority_icon} {priority}\n"
                # Add buttons for employee actions
                keyboard = [
                    [InlineKeyboardButton("✅ Mark as Done", callback_data=f"taskdone_{task_id}"),
                     InlineKeyboardButton("❓ Ask Question", callback_data=f"inquire_{task_id}")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await context.bot.send_message(chat_id=chat_id, text=task_message, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Error in send_active_tasks: {e}")
        await context.bot.send_message(chat_id=chat_id, text="❌ *An error occurred while fetching tasks.*", parse_mode=ParseMode.MARKDOWN)

async def tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unified command to handle viewing and completing tasks for both admin and employees"""
    try:
        chat_id = str(update.message.chat_id)
        is_admin = (chat_id == YOUR_ID)
        employee_name = None if is_admin else get_employee_name(chat_id)
        
        # If employee is not registered, reject the command
        if not is_admin and not employee_name:
            await update.message.reply_text("❌ Only registered employees can use this command!")
            return
        
        # Check if a task_id was provided to mark a task as done
        args = context.args
        if args and args[0].isdigit():
            task_id = int(args[0])
            # Handle task completion
            return await handle_task_completion(update, context, task_id, is_admin, employee_name)
        
        # No task ID provided, show active tasks based on user role
        if is_admin:
            # Admin sees all active tasks
            await update.message.reply_text("📋 Active Tasks:\n\nSelect a task to manage:")
            await send_active_tasks(update.message.chat_id, context)
        else:
            # Employee sees only their tasks
            # Get active tasks from database
            active_tasks = list(db.tasks.find({"status": {"$ne": "completed"}, "completed": {"$ne": True}}))
            
            # Filter tasks for this employee - check both assigned_to and employees fields
            employee_tasks = []
            for task in active_tasks:
                # Check assigned_to field (contains chat_ids)
                assigned_to = task.get('assigned_to', [])
                # Convert all values to strings for comparison
                assigned_to_str = [str(cid) for cid in assigned_to] if isinstance(assigned_to, list) else []
                
                # Check employees field (contains names)
                employees = task.get('employees', [])
                employees_list = employees if isinstance(employees, list) else []
                
                # Add task if either the chat_id is in assigned_to or employee name is in employees
                if str(chat_id) in assigned_to_str or employee_name in employees_list:
                    employee_tasks.append(task)
            
            if not employee_tasks:
                await update.message.reply_text("📝 *You have no active tasks at the moment.*", parse_mode=ParseMode.MARKDOWN)
                return
                
            message = "📋 *Your Active Tasks*\n\n"
            
            # Display each task with action buttons
            for task in employee_tasks:
                task_id = task['task_id']
                task_desc = task['task']
                created_at = task.get('created_at', datetime.now()).strftime('%I:%M %p')
                
                # Enhanced styling for employee task view
                task_message = (
                    f"📋 *Task #{task_id}*\n\n"
                    f"• *Description:* {task_desc}\n"
                    f"• *Created:* {created_at} (UAE)\n"
                )
                
                # Add time allocation if available
                time_allocated = task.get('reminder_interval')
                if time_allocated:
                    task_message += f"• *Time allocated:* {time_allocated} minutes\n"
                    
                # Add due date if available
                due_date = task.get('due_date')
                if due_date:
                    task_message += f"• *Due:* {due_date}\n"
                    
                # Add priority if available
                priority = task.get('priority')
                if priority:
                    priority_icon = "🔴" if priority.lower() == "high" else "🟡" if priority.lower() == "medium" else "🟢"
                    task_message += f"• *Priority:* {priority_icon} {priority}\n"
                
                # Add spacing before buttons
                task_message += "\n"
                
                # Add action buttons for each task
                keyboard = [
                    [
                        InlineKeyboardButton("✅ Mark Done", callback_data=f"taskdone_{task_id}"),
                        InlineKeyboardButton("❓ Ask Question", callback_data=f"inquire_{task_id}")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(task_message, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
            
    except Exception as e:
        logger.error(f"Error in tasks_command: {e}")
        await update.message.reply_text("❌ *An error occurred while fetching tasks.*", parse_mode=ParseMode.MARKDOWN)

async def handle_task_completion(update: Update, context: ContextTypes.DEFAULT_TYPE, task_id: int, is_admin: bool, employee_name: str = None):
    """Handle task completion for both admin and employees"""
    try:
        chat_id = str(update.message.chat_id)
        
        # Get task from database
        task_info = db.get_task(task_id)
        
        if not task_info:
            await update.message.reply_text(f"❌ Task #{task_id} not found!")
            return
        
        # Allow admin to mark any task as done, but employees can only mark their own tasks
        if not is_admin and employee_name not in task_info.get('employees', []):
            await update.message.reply_text("❌ This task is not assigned to you!")
            return
        
        if task_info.get('status') != 'active':
            await update.message.reply_text(f"❌ Task #{task_id} is already completed!")
            return
        
        # Update task status in database
        completer = "Admin" if is_admin else employee_name
        success = db.update_task_status(task_id, 'completed', completer)
        
        if not success:
            await update.message.reply_text(f"❌ Failed to update task status. Please try again.")
            return
        
        # Get updated task info for notification
        updated_task = db.get_task(task_id)
        completed_time = updated_task.get('completed_at', datetime.now()).strftime('%I:%M %p')
        
        # Notify admin (if completed by employee)
        if not is_admin:
            await context.bot.send_message(
                chat_id=YOUR_ID,
                text=f"✅ Task #{task_id} completed by {employee_name}\n"
                     f"Task: {task_info['task']}\n"
                     f"Completed at: {completed_time} (UAE)"
            )
        
        await update.message.reply_text(f"✅ Task #{task_id} marked as completed!")
        
    except Exception as e:
        logger.error(f"Error in handle_task_completion: {e}")
        await update.message.reply_text("❌ Failed to process command. Please try again.")

# Keep the original done_command as a wrapper around tasks_command for backward compatibility
async def done_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Wrapper around tasks_command for backward compatibility"""
    return await tasks_command(update, context)

async def clarify_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /clarify command for admin to add details to tasks"""
    try:
        chat_id = str(update.message.chat_id)
        
        if chat_id != YOUR_ID:
            await update.message.reply_text("❌ Only admin can use this command.")
            return
            
        args = context.args
        if len(args) < 2:
            await update.message.reply_text(
                "❌ Usage: /clarify <task_id> <clarification_text>\n\n"
                "Example: /clarify 25 Please check the inventory first"
            )
            return
            
        # Extract task ID and clarification text
        task_id = None
        try:
            task_id = int(args[0])
        except ValueError:
            await update.message.reply_text("❌ Task ID must be a number.")
            return
            
        # Get the clarification text (everything after the task ID)
        clarification_text = " ".join(args[1:])
        
        # Check if task exists in MongoDB
        task = db.tasks.find_one({"task_id": task_id})
        if not task:
            await update.message.reply_text(f"❌ Task #{task_id} not found!")
            return
            
        if task.get('status') == 'completed' or task.get('completed', False):
            await update.message.reply_text(f"❌ Task #{task_id} is already completed. Cannot add clarification.")
            return
            
        # Add clarification to task in MongoDB
        clarification = {
            "text": clarification_text,
            "timestamp": datetime.now()
        }
        
        # Update task with new clarification
        result = db.tasks.update_one(
            {"task_id": task_id},
            {"$push": {"clarifications": clarification}}
        )
        
        if result.modified_count == 0:
            await update.message.reply_text(f"❌ Failed to add clarification to Task #{task_id}.")
            return
        
        # Send confirmation to admin
        await update.message.reply_text(f"✅ Clarification added to Task #{task_id}!\n\n*Task:* {task['task']}\n\n*Clarification:* {clarification_text}", parse_mode=ParseMode.MARKDOWN)
        
        # Notify assigned employees about the clarification
        assigned_to = task.get('assigned_to', [])
        for emp_chat_id in assigned_to:
            try:
                await context.bot.send_message(
                    chat_id=emp_chat_id,
                    text=f"📝 *Task Clarification*\n\n"
                         f"*Task #{task_id}:* {task['task']}\n\n"
                         f"*Clarification:* {clarification_text}",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                logger.error(f"Failed to send clarification to employee {emp_chat_id}: {e}")
            
    except Exception as e:
        logger.error(f"Error in clarify_command: {e}")
        await update.message.reply_text(f"❌ An error occurred: {str(e)}")

async def list_employees_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /list_employees command for admin to view and manage employees"""
    try:
        chat_id = str(update.message.chat_id)
        
        if chat_id != YOUR_ID:
            await update.message.reply_text("❌ Only admin can use this command.")
            return
        
        # Fetch employee data from MongoDB
        await update.message.reply_text("📋 Fetching employee data...")
        
        # Ensure default employees are in MongoDB
        initialize_employees_in_mongodb()
        
        # Get employees directly from MongoDB collection
        employees = list(db.employees.find())
        
        if not employees or len(employees) == 0:
            await update.message.reply_text(
                "📋 No employees registered.\n"
                "To add an employee, use:\n"
                "/add_employee <name> <telegram_id>"
            )
            return
                
        # Build employee list with task counts
        employee_list = []
        logger.info(f"Building list for {len(employees)} employees")
        
        for employee in employees:
            name = employee.get('name')
            emp_id = employee.get('chat_id')
            
            if not name or not emp_id:
                logger.warning(f"Skipping employee with missing data: {employee}")
                continue
                
            logger.info(f"Getting tasks for employee: {name} (ID: {emp_id})")
            
            # Get tasks for this employee directly from MongoDB collection
            tasks = list(db.tasks.find({"assigned_to": {"$in": [emp_id, str(emp_id)]}})) 
            
            # Count active and total tasks
            active_tasks = sum(1 for task in tasks if task.get('status') != 'completed' and task.get('completed', False) != True)
            total_tasks = len(tasks)
            
            employee_list.append(f"👤 {name}\n   📱 ID: {emp_id}\n   📋 Tasks: {active_tasks} active, {total_tasks} total")
        
        if not employee_list:
            await update.message.reply_text(
                "📋 No valid employees found.\n"
                "To add an employee, use:\n"
                "/add_employee <name> <telegram_id>"
            )
            return
            
        message = "📋 Registered Employees:\n\n" + "\n\n".join(employee_list)
        message += "\n\nTo add an employee:\n/add_employee <name> <telegram_id>"
        message += "\n\nTo remove an employee:\n/remove_employee <telegram_id>"
        
        # Create keyboard with buttons for add/remove options
        keyboard = [
            [
                InlineKeyboardButton("➕ Add Employee", callback_data="add_employee_info"),
                InlineKeyboardButton("❌ Remove Employee", callback_data="remove_employee_info")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(message, reply_markup=reply_markup)
        
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
        chat_id = str(update.callback_query.from_user.id)
        
        # Handle task action buttons
        if data.startswith('taskdone_'):
            task_id = int(data.split('_')[1])
            await query.answer()
            
            # Create a mock update with the task ID as an argument
            context.args = [str(task_id)]
            
            # Special handling for admin
            if chat_id == YOUR_ID:
                # Admin is completing a task directly
                task_info = db.get_task(task_id)
                
                if not task_info:
                    await query.message.reply_text(f"❌ Task #{task_id} not found!")
                    return
                
                if task_info['status'] != 'active':
                    await query.message.reply_text(f"❌ Task #{task_id} is already completed!")
                    return
                
                # Update task status in database
                success = db.update_task_status(task_id, 'completed', "Admin")
                
                if not success:
                    await query.message.reply_text(f"❌ Failed to update task status. Please try again.")
                    return
                
                # Get updated task info for notification
                updated_task = db.get_task(task_id)
                completed_time = updated_task.get('completed_at', datetime.now()).strftime('%I:%M %p')
                
                await query.message.reply_text(
                    f"✅ Task #{task_id} marked as completed by Admin!\n"
                    f"Task: {task_info['task']}\n"
                    f"Completed at: {completed_time} (UAE)"
                )
                
                # Edit the original message to show it's completed
                try:
                    await query.message.edit_text(
                        query.message.text + "\n\n✅ COMPLETED",
                        reply_markup=None
                    )
                except Exception as e:
                    logger.error(f"Error editing message: {e}")
            else:
                # Regular employee using taskdone
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
        # Handle command buttons from welcome message
        elif data.startswith('cmd_'):
            command = data.replace('cmd_', '')
            # Show "tasks" instead of "done" for the View Tasks button
            if command == "done":
                command = "tasks"
            await query.answer(f"Running command: {command}")
            
            # Execute the appropriate command directly
            if data == 'cmd_assign':
                await query.message.reply_text(
                    "*Task Assignment Command Format*\n\n"
                    "`/assign employee1,employee2 <task> [time] [p:priority] [due:date]`\n\n"
                    "*Required Parameters:*\n"
                    "• `employee1,employee2` - Comma-separated list of employees\n"
                    "• `<task>` - Task description\n\n"
                    "*Optional Parameters:*\n\n"
                    "*Time Format:*\n"
                    "• `30m` - 30 minutes\n"
                    "• `2h` - 2 hours\n"
                    "• `1d` - 1 day\n\n"
                    "*Priority Options:*\n"
                    "• `p:high` - 🔴 High priority\n"
                    "• `p:medium` - 🟡 Medium priority\n"
                    "• `p:low` - 🟢 Low priority\n\n"
                    "*Due Date Options:*\n"
                    "• `due:today` - Due today\n"
                    "• `due:tomorrow` - Due tomorrow\n"
                    "• `due:nextweek` - Due next week\n"
                    "• `due:YYYY-MM-DD` - Due on specific date\n\n"
                    "*Examples:*\n"
                    "`/assign rehan,shameem Check inventory 30m p:high due:tomorrow`\n"
                    "`/assign rehan Daily report 1d p:medium due:2025-04-20`",
                    parse_mode=ParseMode.MARKDOWN
                )
            elif data == 'cmd_done' or data == 'cmd_tasks':
                # For commands that show task lists, execute them directly
                chat_id = str(query.from_user.id)
                # Set empty args for the context
                context.args = []
                
                # Call the tasks_command directly
                await tasks_command(update, context)

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
            await query.message.reply_text(
                "To add a new employee, use the format:\n"
                "/add_employee <name> <chat_id>\n\n"
                "Example: /add_employee John 123456789"
            )
        elif data == 'add_test_employees':
            await query.answer("Adding test employees...")
            
            try:
                # Check if MongoDB is connected
                if not db.is_connected():
                    # Try to reconnect
                    db.connect()
                    await query.message.reply_text(
                        "⚠️ Database connection was lost. Attempting to reconnect..."
                    )
                    if not db.is_connected():
                        await query.message.reply_text(
                            "❌ Failed to connect to database. Please check with /dbstatus."
                        )
                        return
                
                # Add test employees
                test_employees = [
                    {"name": "John", "chat_id": "123456789"},
                    {"name": "Alice", "chat_id": "987654321"},
                    {"name": "Bob", "chat_id": "555555555"}
                ]
                
                success_count = 0
                for employee in test_employees:
                    try:
                        # Check if employee already exists
                        existing = db.employees.find_one({"chat_id": employee["chat_id"]})
                        if existing:
                            continue
                            
                        # Add employee to database
                        db.employees.insert_one(employee)
                        success_count += 1
                        logger.info(f"Added test employee: {employee['name']} with chat ID {employee['chat_id']}")
                    except Exception as e:
                        logger.error(f"Error adding test employee {employee['name']}: {e}")
                
                if success_count > 0:
                    await query.message.reply_text(f"✅ Added {success_count} test employees successfully!")
                else:
                    await query.message.reply_text("⚠️ No new test employees were added. They may already exist.")
                
                # Show updated employee list
                employees = list(db.employees.find())
                
                # Create a message with all employees
                message = "📋 *Employee List*\n\n"
                
                # Create keyboard with remove buttons
                keyboard = []
                
                for i, employee in enumerate(employees, 1):
                    name = employee.get('name', 'Unknown')
                    employee_chat_id = employee.get('chat_id', 'Unknown')
                    
                    message += f"{i}. 👤 *{name}* (ID: `{employee_chat_id}`)\n"
                    
                    # Add remove button for each employee
                    keyboard.append([
                        InlineKeyboardButton(f"❌ Remove {name}", callback_data=f"remove_employee_{employee_chat_id}")
                    ])
                
                # Add a button to add new employees
                keyboard.append([InlineKeyboardButton("➕ Add Employee", callback_data="add_employee")])
                
                # Send the message with the inline keyboard
                await query.message.reply_text(
                    message,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode=ParseMode.MARKDOWN
                )
                
            except Exception as e:
                logger.error(f"Error adding test employees: {e}")
                await query.message.reply_text(f"❌ Error adding test employees: {str(e)}")
        elif data.startswith('remove_employee_'):
            # Extract employee chat ID from callback data
            employee_chat_id = data.split('_')[2]
            
            # Only admin can remove employees
            if chat_id != YOUR_ID:
                await query.answer("⛔ Only administrators can remove employees")
                return
                
            await query.answer("Removing employee...")
            
            try:
                # Check if MongoDB is connected
                if not db.is_connected():
                    await query.message.reply_text(
                        "⚠️ Database connection error. Please try again later or check with /dbstatus."
                    )
                    return
                
                # Check if employee exists
                existing_employee = db.employees.find_one({'chat_id': employee_chat_id})
                if not existing_employee:
                    await query.message.reply_text(
                        f"⚠️ No employee found with chat ID {employee_chat_id}."
                    )
                    return
                
                # Remove employee from database
                result = db.employees.delete_one({'chat_id': employee_chat_id})
                
                if result.deleted_count > 0:
                    logger.info(f"Removed employee: {existing_employee['name']} with chat ID {employee_chat_id}")
                    
                    # Confirm to admin
                    await query.message.reply_text(
                        f"✅ Employee removed successfully!\n\n"
                        f"👤 Name: {existing_employee['name']}\n"
                        f"📱 Chat ID: {employee_chat_id}"
                    )
                    
                    # Try to notify the employee if possible
                    try:
                        await context.bot.send_message(
                            chat_id=employee_chat_id,
                            text="🔔 Your account has been removed from the TrichyGold Task Manager system by the administrator."
                        )
                    except Exception as e:
                        logger.error(f"Failed to notify removed employee: {e}")
                    
                    # Show updated employee list after successful removal
                    # Get all employees from database
                    employees = list(db.employees.find())
                    
                    if not employees:
                        await query.message.reply_text("📋 No employees found in the system.")
                        return
                    
                    # Create a message with all employees
                    message = "📋 *Updated Employee List*\n\n"
                    
                    # Create keyboard with remove buttons
                    keyboard = []
                    
                    for i, employee in enumerate(employees, 1):
                        name = employee.get('name', 'Unknown')
                        employee_chat_id = employee.get('chat_id', 'Unknown')
                        
                        message += f"{i}. 👤 *{name}* (ID: `{employee_chat_id}`)\n"
                        
                        # Add remove button for each employee
                        keyboard.append([
                            InlineKeyboardButton(f"❌ Remove {name}", callback_data=f"remove_employee_{employee_chat_id}")
                        ])
                    
                    # Add a button to add new employees
                    keyboard.append([InlineKeyboardButton("➕ Add Employee", callback_data="add_employee")])
                    
                    # Send the message with the inline keyboard
                    await query.message.reply_text(
                        message,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    await query.message.reply_text(
                        f"❌ Failed to remove employee with chat ID {employee_chat_id}."
                    )
                    
            except Exception as e:
                logger.error(f"Error removing employee: {e}")
                await query.message.reply_text(
                    f"❌ Error removing employee: {str(e)}\n\n"
                    f"Please try again or check database connection with /dbstatus."
                )
            
    except Exception as e:
        logger.error(f"Error in handle_button_callback: {e}")
        await query.answer("❌ An error occurred")

async def taskdone_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Wrapper around tasks_command for backward compatibility"""
    return await tasks_command(update, context)

async def mytasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Wrapper around tasks_command for backward compatibility"""
    return await tasks_command(update, context)

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
        
        # Check if message text was provided
        args = context.args
        if not args:
            await update.message.reply_text(
                "❌ Usage: /broadcast <message>\n\n"
                "Example: /broadcast Meeting at 3pm today"
            )
            return
            
        # Get the broadcast message
        broadcast_message = " ".join(args)
        
        # Get all employees from database
        employees = list(db.employees.find())
        if not employees:
            await update.message.reply_text("❌ No employees found to broadcast to.")
            return
            
        # Send the broadcast message to all employees
        success_count = 0
        fail_count = 0
        
        for employee in employees:
            emp_chat_id = employee.get('chat_id')
            try:
                await context.bot.send_message(
                    chat_id=emp_chat_id,
                    text=f"📢 *Broadcast Message*\n\n{broadcast_message}",
                    parse_mode=ParseMode.MARKDOWN
                )
                success_count += 1
            except Exception as e:
                logger.error(f"Failed to send broadcast to {emp_chat_id}: {e}")
                fail_count += 1
                
        # Send confirmation to admin
        status = f"✅ Broadcast sent to {success_count} employees"
        if fail_count > 0:
            status += f"\n❌ Failed to send to {fail_count} employees"
            
        await update.message.reply_text(status)
        
    except Exception as e:
        logger.error(f"Error in broadcast_command: {e}")
        await update.message.reply_text(f"❌ An error occurred: {str(e)}")

async def send_task_reminder(context: ContextTypes.DEFAULT_TYPE):
    """Send reminder for specific task"""
    try:
        job = context.job
        task_id = job.data['task_id']
        
        logger.info(f"Sending reminder for Task #{task_id}")
        
        # Get task from database
        task = db.tasks.find_one({"task_id": task_id})
        
        if not task:
            logger.error(f"Task #{task_id} not found for reminder")
            job.schedule_removal()
            return
            
        if task.get('status') == 'completed' or task.get('completed', False):
            logger.info(f"Task #{task_id} is already completed, removing reminder job")
            job.schedule_removal()
            return
            
        # Format reminder message
        task_desc = task.get('task', 'No description')
        
        # Add priority if available
        priority_text = ""
        priority = task.get('priority')
        if priority:
            priority_icon = "🔴" if priority.lower() == "high" else "🟡" if priority.lower() == "medium" else "🟢"
            priority_text = f"*Priority:* {priority_icon} {priority.capitalize()}\n"
            
        # Add due date if available
        due_date_text = ""
        due_date = task.get('due_date')
        if due_date:
            due_date_text = f"*Due Date:* {due_date}\n"
            
        # Add assigned date if available
        assigned_date_text = ""
        assigned_date = task.get('assigned_date')
        if assigned_date:
            assigned_date_text = f"*Assigned:* {assigned_date}\n"
            
        # Create reminder message
        reminder_message = (
            f"⏰ *Task Reminder*\n\n"
            f"*Task #{task_id}:* {task_desc}\n"
            f"{priority_text}"
            f"{due_date_text}"
            f"{assigned_date_text}\n"
            f"Use the buttons below to manage this task."
        )
        
        # Create keyboard with done button
        keyboard = [
            [InlineKeyboardButton("✅ Mark as Done", callback_data=f"taskdone_{task_id}"),
             InlineKeyboardButton("❓ Ask Question", callback_data=f"inquire_{task_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Send reminder to each assigned employee
        assigned_to = task.get('assigned_to', [])
        success_count = 0
        
        for emp_chat_id in assigned_to:
            try:
                await context.bot.send_message(
                    chat_id=emp_chat_id,
                    text=reminder_message,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )
                success_count += 1
            except Exception as e:
                logger.error(f"Failed to send reminder to {emp_chat_id}: {e}")
                
        logger.info(f"Sent reminder for Task #{task_id} to {success_count} employees")
        
    except Exception as e:
        logger.error(f"Error in send_task_reminder: {e}")
        # Don't remove the job on error, it will retry next time

async def task_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /task command to view tasks assigned to a specific employee"""
    try:
        chat_id = str(update.message.chat_id)
        
        # Only admin can use this command
        if chat_id != YOUR_ID:
            await update.message.reply_text("❌ This command is only for admin use.")
            return
        
        # Check if employee name was provided
        args = context.args
        if not args:
            await update.message.reply_text("❌ Usage: /task <employee_name>\n\nExample: /task Rehan")
            return
        
        # Get employee name from args
        employee_name = " ".join(args).strip()
        
        # Get all employees directly from MongoDB
        employees = list(db.employees.find())
        
        # Find the employee with the given name (more flexible matching)
        employee_id = None
        for emp in employees:
            # Check if the employee name contains the search term (case insensitive)
            if employee_name.lower() in emp.get('name', '').lower():
                employee_id = emp.get('chat_id')
                employee_name = emp.get('name')  # Use the correct case
                break
        
        if not employee_id:
            await update.message.reply_text(f"❌ *No employee found with name '{employee_name}'.*\n\nUse /list_employees to see all registered employees.", parse_mode=ParseMode.MARKDOWN)
            return
        
        # Get tasks assigned to this employee directly from MongoDB
        # Use a more comprehensive query to find tasks assigned to this employee
        tasks = list(db.tasks.find({
            "$or": [
                {"assigned_to": {"$in": [employee_id, str(employee_id)]}},
                {"employees": {"$in": [employee_name]}}
            ]
        }))
        
        # Log task details for debugging
        logger.info(f"Found {len(tasks)} tasks for employee {employee_name} (ID: {employee_id})")
        
        if not tasks:
            await update.message.reply_text(f"📋 *{employee_name} has no tasks assigned.*", parse_mode=ParseMode.MARKDOWN)
            return
        
        # Group tasks by status
        active_tasks = [t for t in tasks if t.get('status') != 'completed' and t.get('completed', False) != True]
        completed_tasks = [t for t in tasks if t.get('status') == 'completed' or t.get('completed', False) == True]
        
        # Display active tasks
        if active_tasks:
            message = f"📋 *Active Tasks for {employee_name}*\n\n"
            for task in active_tasks:
                task_id = task['task_id']
                message += (
                    f"*Task #{task_id}*\n"
                    f"• *Description:* {task['task']}\n"
                    f"• *Time allocated:* {task.get('reminder_interval', 'Not specified')} minutes\n\n"
                )
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text(f"📋 *{employee_name} has no active tasks.*", parse_mode=ParseMode.MARKDOWN)
        
        # Display completed tasks (last 5)
        if completed_tasks:
            # Sort by completion time (newest first) and take last 5
            completed_tasks.sort(key=lambda x: x.get('completed_at', datetime.min), reverse=True)
            recent_completed = completed_tasks[:5]
            message = f"📋 *Recently Completed Tasks for {employee_name}*\n\n"
            for task in recent_completed:
                task_id = task['task_id']
                message += (
                    f"✅ *Task #{task_id}*\n"
                    f"• *Description:* {task['task']}\n"
                    f"• *Completed:* {task.get('completed_at', datetime.now()).strftime('%I:%M %p')} (UAE)\n\n"
                )
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Error in task_command: {e}")
        await update.message.reply_text("❌ *An error occurred while fetching tasks.*", parse_mode=ParseMode.MARKDOWN)

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
        task_info = db.get_task(task_id)
        
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

async def handle_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks"""
    try:
        query = update.callback_query
        data = query.data
        chat_id = str(update.callback_query.from_user.id)
        
        # Log the button press
        logger.info(f"Button callback: {data} from user {chat_id}")
        
        # Handle employee removal buttons
        if data.startswith('remove_emp_'):
            # Only admin can remove employees
            if chat_id != YOUR_ID:
                await query.answer("⛔ Only admin can remove employees")
                return
                
            # Extract employee chat ID from callback data
            employee_chat_id = data.split('_')[2]
            
            # Confirm removal with the admin
            keyboard = [
                [InlineKeyboardButton("✅ Yes, remove", callback_data=f"confirm_remove_{employee_chat_id}")],
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel_remove")]
            ]
            
            # Get employee name for confirmation message
            employee = db.get_employee(employee_chat_id)
            if employee and 'name' in employee:
                employee_name = employee['name']
                await query.message.reply_text(
                    f"⚠️ Are you sure you want to remove employee {employee_name} (ID: {employee_chat_id})?\n\n"
                    f"This action cannot be undone.",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            else:
                await query.answer("❌ Employee not found")
            
        # Handle employee removal confirmation
        elif data.startswith('confirm_remove_'):
            # Only admin can remove employees
            if chat_id != YOUR_ID:
                await query.answer("⛔ Only admin can remove employees")
                return
                
            # Extract employee chat ID from callback data
            employee_chat_id = data.split('_')[2]
            
            # Remove employee from database
            success, message, employee_data = db.remove_employee(employee_chat_id)
            
            if success:
                # Confirm to admin
                await query.message.reply_text(
                    f"✅ Employee removed successfully!\n\n"
                    f"👤 Name: {employee_data['name']}\n"
                    f"📱 Chat ID: {employee_chat_id}"
                )
                
                # Try to notify the employee if possible
                try:
                    await context.bot.send_message(
                        chat_id=employee_chat_id,
                        text="🔔 Your account has been removed from the TrichyGold Task Manager system by the administrator."
                    )
                except Exception as e:
                    logger.error(f"Failed to notify removed employee: {e}")
                    
                # Refresh the employee list
                await list_employees_command(update, context)
            else:
                await query.message.reply_text(f"❌ {message}")
                
        # Handle cancellation of employee removal
        elif data == 'cancel_remove':
            await query.message.reply_text("🔄 Employee removal cancelled.")
            
        # Handle add employee button
        elif data == 'add_employee':
            await query.message.reply_text(
                "To add a new employee, use the command:\n"
                "/add_employee <name> <telegram_id>\n\n"
                "Example: /add_employee john 123456789"
            )
            
        # Handle other button callbacks
        elif data.startswith('taskdone_'):
            task_id = int(data.split('_')[1])
            await query.answer()
            
            # Create a mock update with the task ID as an argument
            context.args = [str(task_id)]
            
            # Call the taskdone command
            await taskdone_command(update, context)
            
        elif data.startswith('inquire_'):
            task_id = int(data.split('_')[1])
            await query.answer()
            
            # Set up context for inquiry
            context.user_data['inquiring_task'] = task_id
            
            await query.message.reply_text(
                f"📝 Send your question about Task #{task_id}\n"
                f"You can send:\n"
                f"• Text message\n"
                f"• Voice message\n"
                f"• Files/documents\n"
                f"• Photos"
            )
            
    except Exception as e:
        logger.error(f"Error in handle_button_callback: {e}")
        await query.answer("❌ An error occurred")

async def log_all_updates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log all incoming updates for debugging"""
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

# Add a ping endpoint for uptime monitoring
@app.route('/ping')
async def ping():
    logger.info("Ping received from uptime monitor")
    return "Pong", 200

async def mark_task_done(task_id: str, chat_id: str) -> bool:
    """Mark a task as done and return success status"""
    try:
        # Check if database is connected
        if not db.is_connected():
            db.connect()
            if not db.is_connected():
                logger.error("Database connection failed in mark_task_done")
                return False
                
        # Get task from database
        task = db.tasks.find_one({"task_id": int(task_id), "completed": False})
        
        if not task:
            logger.error(f"Task {task_id} not found or already completed")
            return False
            
        # Update task as completed
        result = db.tasks.update_one(
            {"task_id": int(task_id)},
            {"$set": {"completed": True, "completed_by": chat_id, "completed_at": datetime.now()}}
        )
        
        if result.modified_count > 0:
            logger.info(f"Task {task_id} marked as completed by {chat_id}")
            return True
        else:
            logger.error(f"Failed to update task {task_id}")
            return False
    except Exception as e:
        logger.error(f"Error in mark_task_done: {e}")
        return False

async def db_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /dbstatus command to check MongoDB connection status"""
    chat_id = update.message.chat_id
    user_id = str(chat_id)
    
    # Get connection status
    is_connected = db.is_connected()
    connection_details = db.get_connection_status()
    
    # Try to reconnect if not connected
    if not is_connected:
        await update.message.reply_text("⚠️ Database not connected. Attempting to reconnect...")
        db.connect()
        is_connected = db.is_connected()
        connection_details = db.get_connection_status()
    
    if is_connected:
        # Get more detailed information
        try:
            # Check if employees collection exists and count documents
            try:
                employee_count = db.employees.count_documents({})
                collection_status = f"✅ Employees collection: {employee_count} employees found"
            except Exception as coll_err:
                collection_status = f"❌ Employees collection error: {str(coll_err)}"
            
            message = (
                f"✅ MongoDB Connection Status: CONNECTED\n\n"
                f"Database: {db.db.name}\n"
                f"Last Connection Attempt: {connection_details.get('last_attempt', 'unknown')}\n\n"
                f"{collection_status}\n\n"
                f"Storage Mode: MongoDB\n\n"
                f"Commands:\n"
                f"/dbreconnect - Force reconnection attempt\n"
                f"/dbmigrate - Migrate in-memory data to MongoDB\n"
                f"/add_test_employees - Add test employees to database"
            )
            
            # Create keyboard with database actions
            keyboard = [
                [InlineKeyboardButton("🔄 Reconnect", callback_data="cmd_dbreconnect")],
                [InlineKeyboardButton("➕ Add Test Employees", callback_data="add_test_employees")],
                [InlineKeyboardButton("📋 List Employees", callback_data="cmd_list_employees")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
        except Exception as e:
            message = (
                f"✅ MongoDB Connection Status: CONNECTED\n\n"
                f"Could not retrieve detailed info: {str(e)}\n\n"
                f"Storage Mode: MongoDB\n\n"
                f"Commands:\n"
                f"/dbreconnect - Force reconnection attempt\n"
                f"/dbmigrate - Migrate in-memory data to MongoDB"
            )
            reply_markup = None
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
        
        # Create keyboard with reconnect action
        keyboard = [
            [InlineKeyboardButton("🔄 Reconnect", callback_data="cmd_dbreconnect")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        text=message,
        reply_markup=reply_markup
    )
    
    # Add a direct command to add test employees
    if is_connected:
        await update.message.reply_text(
            "You can add test employees directly with:\n"
            "/add_test_employees"
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
    chat_id = str(update.message.chat_id)
    
    # Only admin can migrate data
    if chat_id != YOUR_ID:
        await update.message.reply_text("⛔ Sorry, only administrators can migrate data.")
        return
    
    # Check if MongoDB is connected
    if not db.is_connected():
        await update.message.reply_text(
            "⚠️ Database connection error. Please check with /dbstatus and try again."
        )
        return
    
    # Migrate data
    try:
        # TODO: Implement data migration logic
        await update.message.reply_text(
            "✅ Data migration feature is not yet implemented."
        )
    except Exception as e:
        logger.error(f"Error in db_migrate_command: {e}")
        await update.message.reply_text(f"❌ Error migrating data: {str(e)}")

async def remove_employee_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /remove_employee command to remove an employee from the system"""
    chat_id = str(update.message.chat_id)
    
    # Only admin can remove employees
    if chat_id != YOUR_ID:
        await update.message.reply_text("⛔ Sorry, only administrators can remove employees.")
        return
    
    # Check if we have the required arguments
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "⚠️ Please provide employee chat ID.\n\n"
            "Format: /remove_employee <chat_id>\n"
            "Example: /remove_employee 123456789"
        )
        return
    
    # Extract chat_id from arguments
    employee_chat_id = context.args[0]
    
    # Validate chat ID
    from validators import is_valid_chat_id
    if not is_valid_chat_id(employee_chat_id):
        await update.message.reply_text("⚠️ Invalid chat ID format.")
        return
    
    # Remove employee from database
    success, message, employee_data = db.remove_employee(employee_chat_id)
    
    if success:
        # Confirm to admin
        await update.message.reply_text(
            f"✅ Employee removed successfully!\n\n"
            f"👤 Name: {employee_data['name']}\n"
            f"📱 Chat ID: {employee_chat_id}"
        )
        
        # Try to notify the employee if possible
        try:
            await context.bot.send_message(
                chat_id=employee_chat_id,
                text="🔔 Your account has been removed from the TrichyGold Task Manager system by the administrator."
            )
        except Exception as e:
            logger.error(f"Failed to notify removed employee: {e}")
    else:
        await update.message.reply_text(f"❌ {message}")


@app.route('/webhook', methods=['POST'])
async def webhook():
    """Handle incoming webhook requests from Telegram
    
    This optimized handler properly manages connections and prevents resource leaks
    that could cause VPN alerts during idle periods.
    """
    # Use a single try-except block for the entire handler to ensure proper cleanup
    try:
        # Set a reasonable timeout for JSON parsing
        try:
            data = await asyncio.wait_for(request.get_json(), timeout=2.0)
        except asyncio.TimeoutError:
            logger.warning("Webhook request JSON parsing timed out")
            return "OK", 200  # Return OK to prevent Telegram from retrying
        except Exception as e:
            logger.error(f"Error parsing webhook request: {e}")
            return "OK", 200
            
        # Minimal logging to reduce network traffic
        log_update_type(data)
        
        # Create an Update object from the JSON data
        update = Update.de_json(data, application.bot)
        if not update:
            logger.warning("Invalid update data received")
            return "OK", 200
            
        # Process the update based on its type
        if update.callback_query:
            # Handle callback queries (button presses)
            await handle_callback_query(update.callback_query)
        elif update.message:
            # Handle regular messages and commands
            try:
                # Set a timeout for processing to prevent hanging
                await asyncio.wait_for(application.process_update(update), timeout=4.0)
            except asyncio.TimeoutError:
                logger.error("Message processing timed out")
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                
        # Always return OK to prevent Telegram from retrying
        return "OK", 200
            
    except Exception as e:
        logger.error(f"Unhandled webhook error: {e}")
        return "OK", 200
        
# Helper function to log update types with minimal information
def log_update_type(data):
    """Log minimal information about the update type"""
    try:
        if 'callback_query' in data:
            callback_data = data.get('callback_query', {}).get('data', '')
            logger.info(f"Received callback: {callback_data[:20]}" + ("..." if len(callback_data) > 20 else ""))
        elif 'message' in data and 'text' in data.get('message', {}):
            message_text = data.get('message', {}).get('text', '')
            if message_text.startswith('/'):
                command = message_text.split()[0]
                logger.info(f"Received command: {command}")
            else:
                logger.info("Received text message")
        else:
            logger.info("Received non-text update")
    except Exception as e:
        logger.error(f"Error logging update type: {e}")

# Helper function to handle callback queries
async def handle_callback_query(query):
    """Handle callback queries (button presses) with proper resource management"""
    try:
        # Acknowledge the button press with minimal data and a short timeout
        try:
            await asyncio.wait_for(query.answer(), timeout=1.0)
        except Exception:
            pass  # Continue even if acknowledgment fails
        
        data = query.data
        chat_id = str(query.from_user.id)
        
        # Use the button_handlers module to handle the callback
        # This avoids creating mock updates and contexts
        from button_handlers import process_button_callback
        await process_button_callback(query, application.bot)
        
    except Exception as e:
        logger.error(f"Error handling callback query: {e}")

async def main() -> None:
    """Start the bot."""
    try:
        # Use the global application instance instead of creating a new one
        global application
        
        # First, initialize the application
        await application.initialize()
        
        logger.info("Initializing application and registering command handlers...")

        # Command handlers
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("assign", assign_task))
        application.add_handler(CommandHandler("done", done_command))
        application.add_handler(CommandHandler("clarify", clarify_command))
        application.add_handler(CommandHandler("inquire", inquire_command))
        application.add_handler(CommandHandler("taskdone", taskdone_command))
        application.add_handler(CommandHandler("tasks", tasks_command))  # New unified command
        application.add_handler(CommandHandler("notify", notify_command))
        application.add_handler(CommandHandler("broadcast", broadcast_command))
        application.add_handler(CommandHandler("list_employees", list_employees_command))
        application.add_handler(CommandHandler("task", task_command))
        application.add_handler(CommandHandler("dbstatus", db_status_command))
        application.add_handler(CommandHandler("dbreconnect", db_reconnect_command))
        application.add_handler(CommandHandler("dbmigrate", db_migrate_command))
        application.add_handler(CommandHandler("add_employee", add_employee_command))
        application.add_handler(CommandHandler("remove_employee", remove_employee_command))
        application.add_handler(CommandHandler("add_test_employees", add_test_employees_command))
        
        # IMPORTANT: Register the callback query handler for button clicks
        application.add_handler(CallbackQueryHandler(handle_button_callback))
        logger.info("Registered callback query handler for button clicks")
        
        # Media message handler for clarifications, inquiries, and broadcasts
        # Only handle non-command messages
        application.add_handler(MessageHandler(
            (filters.TEXT | filters.VOICE | filters.Document.ALL | filters.PHOTO) & ~filters.COMMAND,
            handle_media_message
        ))

        # Add error handler
        application.add_error_handler(error_handler)
        
        logger.info("All handlers registered successfully")

        # Add detailed logging for all updates
        async def log_all_updates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            """Log all updates for debugging purposes"""
            try:
                logger.info(f"Received update with ID: {update.update_id}")
                
                if update.message:
                    user = update.message.from_user
                    user_id = user.id if user else "Unknown"
                    username = user.username if user else "None"
                    logger.info(f"MESSAGE: {update.message.text} from user {user_id} ({username})")
                    
                    # Log commands specifically
                    if update.message.text and update.message.text.startswith('/'):
                        command_parts = update.message.text.split()
                        command = command_parts[0]
                        args = command_parts[1:] if len(command_parts) > 1 else []
                        logger.info(f"COMMAND DETECTED: {command}")
                        logger.info(f"Command: {command}, Args: {args}")
                        
                elif update.callback_query:
                    user = update.callback_query.from_user
                    user_id = user.id if user else "Unknown"
                    logger.info(f"Button callback: {update.callback_query.data} from user {user_id}")
                    
                # Don't block the update from being processed by other handlers
            except Exception as e:
                logger.error(f"Error in logging update: {e}")

        application.add_handler(MessageHandler(filters.ALL, log_all_updates), group=999)

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
                
            # Set up webhook with reduced connection frequency
            try:
                # Get the webhook info with a timeout to avoid hanging connections
                try:
                    webhook_info = await asyncio.wait_for(application.bot.get_webhook_info(), timeout=5.0)
                    logger.info(f"Current webhook URL: {webhook_info.url}")
                    
                    # Only update webhook if it's not already set correctly
                    webhook_url = f"{service_url}/webhook"
                    
                    if webhook_info.url != webhook_url:
                        # Delete existing webhook
                        logger.info("Deleting existing webhook...")
                        await asyncio.wait_for(application.bot.delete_webhook(), timeout=5.0)
                        
                        # Set up webhook with a short max_connections to reduce network traffic
                        logger.info(f"Setting webhook URL to: {webhook_url}")
                        await asyncio.wait_for(
                            application.bot.set_webhook(
                                webhook_url,
                                max_connections=1,  # Reduce concurrent connections
                                drop_pending_updates=True  # Ignore old updates to reduce traffic
                            ), 
                            timeout=5.0
                        )
                        logger.info("Webhook setup complete!")
                    else:
                        logger.info("Webhook already correctly configured, skipping update")
                except asyncio.TimeoutError:
                    logger.error("Webhook setup timed out, continuing with current configuration")
                except Exception as e:
                    logger.error(f"Error setting up webhook: {e}")
            except Exception as e:
                logger.error(f"Webhook setup failed: {e}")
            
            # Register commands with BotFather
            logger.info("Registering commands with BotFather...")
            from telegram import BotCommand
            # Fix for BotCommandScopeChat import
            try:
                from telegram.constants import BotCommandScopeChat
            except ImportError:
                # Fallback for older python-telegram-bot versions
                from telegram import BotCommandScopeChat
            # First set default commands for all users (only employee commands)
            employee_commands = [
                BotCommand("start", "Start the bot and show main menu"),
                BotCommand("help", "Show help information"),
                BotCommand("tasks", "View your tasks"),
                BotCommand("notify", "Send message to admin")
            ]
            # Set these as the default commands for all users
            await application.bot.set_my_commands(employee_commands)
            
            # Then set admin-specific commands just for the admin user
            # Use YOUR_ID directly instead of comparing with chat_id which isn't defined here
            admin_commands = [
                BotCommand("start", "Start the bot and show main menu"),
                BotCommand("help", "Show help information"),
                BotCommand("assign", "Assign tasks to employees"),
                BotCommand("tasks", "View and manage all tasks"),
                BotCommand("task", "View tasks for specific employee"),
                BotCommand("list_employees", "List all employees"),
                BotCommand("add_employee", "Add a new employee"),
                BotCommand("remove_employee", "Remove an employee")
            ]
            # Override commands just for the admin
            try:
                from telegram.constants import BotCommandScopeChat
            except ImportError:
                # Fallback for older python-telegram-bot versions
                from telegram import BotCommandScopeChat
            await application.bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(YOUR_ID))
            
            # Verify webhook setup
            webhook_info = await application.bot.get_webhook_info()
            logger.info(f"Webhook URL: {webhook_info.url}")
            logger.info(f"Pending update count: {webhook_info.pending_update_count}")
            if webhook_info.last_error_message:
                logger.warning(f"Webhook last error: {webhook_info.last_error_message}")
                
            # Start the webhook server
            logger.info(f"Starting webhook server on port {port}")
            await server.serve()
        else:
            # Local development - polling mode
            logger.info("Local development detected. Running in polling mode.")
            await application.bot.delete_webhook()
            
            # Start the web server in a separate task
            web_server_task = asyncio.create_task(server.serve())
            
            # Log_all_updates is already registered above, no need to register it again
            
            # Application is already initialized above
            
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