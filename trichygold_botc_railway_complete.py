import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
from datetime import datetime, time
import pytz
import logging
import os
import re
import copy

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Get and log the bot token (without showing the full token for security)
BOT_TOKEN = os.getenv('BOT_TOKEN', '')
if not BOT_TOKEN:
    logger.error("BOT_TOKEN environment variable not set!")
    logger.error("Make sure to set the BOT_TOKEN environment variable in Railway dashboard")
    
token_preview = BOT_TOKEN[:10] + '...' if BOT_TOKEN and len(BOT_TOKEN) > 10 else 'Not set'
logger.info(f"Using bot token: {token_preview}")

# Set YOUR_ID to a default value that matches your Telegram ID
YOUR_ID = os.getenv('ADMIN_ID', '1341853859')  # Default to shameem's ID
logger.info(f"Admin ID set to: {YOUR_ID}")

# Initialize database and bot
from database import db
from employee_handlers import add_employee_command, remove_employee_command, list_employees_command
from test_employees import add_test_employees_command
from button_handlers import handle_button_callback
application = Application.builder().token(BOT_TOKEN).build()
application.bot_data['ADMIN_ID'] = YOUR_ID

# Helper functions
async def format_task_message(task, chat_id):
    """Format a task message with proper time display, priority, and due date"""
    minutes = task.get('reminder_interval')
    priority = task.get('priority', 'normal')
    due_date = task.get('due_date')
    assigned_date = task.get('assigned_at')
    
    message = f"📊 Task #{task['task_id']}\n"
    message += f"• Description: {task['task']}\n"
    message += f"• Priority: {priority}\n"
    if minutes:
        message += f"• Time: {minutes} minutes\n"
    if due_date:
        message += f"• Due: {due_date}\n"
    if assigned_date:
        message += f"• Assigned: {assigned_date.strftime('%Y-%m-%d %H:%M')}\n"
    
    # Add assigned to information for admin
    if str(chat_id) == YOUR_ID:
        assigned_to = task.get('assigned_to', [])
        if assigned_to:
            employee_names = []
            for emp_id in assigned_to:
                emp = db.employees.find_one({'chat_id': str(emp_id)})
                if emp:
                    employee_names.append(emp['name'])
            if employee_names:
                message += f"• Assigned to: {', '.join(employee_names)}\n"
    
    return message

async def send_task_reminder(context: ContextTypes.DEFAULT_TYPE):
    """Send reminder for specific task"""
    try:
        task_id = context.job.data['task_id']
        chat_id = context.job.data['chat_id']
        
        # Get task from database
        task = db.tasks.find_one({'task_id': task_id})
        if not task:
            logger.error(f"Task {task_id} not found in database")
            return
            
        # Format and send reminder
        message = await format_task_message(task, chat_id)
        message += "\n⏰ Reminder: This task is still pending."
        
        # Create keyboard with task completion button
        keyboard = [[InlineKeyboardButton("✅ Mark as Done", callback_data=f"taskdone_{task_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(
            chat_id=chat_id,
            text=message,
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Error in send_task_reminder: {e}")

async def log_all_updates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log all incoming updates for debugging"""
    try:
        if update.message:
            logger.info(f"Message from {update.message.from_user.id}: {update.message.text}")
        elif update.callback_query:
            logger.info(f"Callback query from {update.callback_query.from_user.id}: {update.callback_query.data}")
        else:
            logger.info(f"Update received: {update}")
    except Exception as e:
        logger.error(f"Error logging update: {e}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors in the telegram bot."""
    try:
        logger.error(f"Error in update {update}: {context.error}")
        
        # Send error message to admin
        if YOUR_ID:
            error_msg = f"⚠️ Bot Error\n\n"
            error_msg += f"Update: {update}\n\n"
            error_msg += f"Error: {str(context.error)}"
            
            try:
                await context.bot.send_message(
                    chat_id=YOUR_ID,
                    text=error_msg,
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                logger.error(f"Failed to notify admin: {e}")
    except Exception as e:
        logger.error(f"Error in error handler: {e}")

# Command Handlers
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
        help_text = r"""
🔑 *Admin Commands*

/assign - Assign tasks to employees
Format: /assign employee1,employee2 task [time] [priority] [due_date]

/tasks - View and manage all active tasks
Format: /tasks [task_id]

/clarify - Add details to tasks
Format: /clarify task_id details

/broadcast - Send message to all employees
Format: /broadcast message

/list_employees - View all registered employees

/add_employee - Add a new employee
Format: /add_employee name chat_id

/remove_employee - Remove an employee
Format: /remove_employee chat_id

/task - View tasks assigned to a specific employee
Format: /task employee_name

/dbstatus - Check database connection status

/help - Show this message

*Legacy Commands* (use /tasks instead):
/done - Same as /tasks
"""
        
        # Create keyboard with admin quick actions
        keyboard = [
            [InlineKeyboardButton("📋 List Employees", callback_data="cmd_list_employees")],
            [InlineKeyboardButton("📝 Assign Task", callback_data="cmd_assign")],
            [InlineKeyboardButton("📊 View Tasks", callback_data="cmd_tasks")]
        ]
    else:
        help_text = r"""
👤 *Employee Commands*

/tasks - View your tasks and mark them as completed
Format: /tasks [task_id]

/inquire - Ask questions about tasks
Format: /inquire task_id question

/notify - Send notice to admin
Format: /notify message

/help - Show this message

*Legacy Commands* (use /tasks instead):
/taskdone - Same as /tasks
/mytasks - Same as /tasks
"""
        
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

# Command Handlers
async def assign_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /assign command for task assignment"""
    try:
        chat_id = str(update.message.chat_id)
        if chat_id != YOUR_ID:
            await update.message.reply_text("❌ Only admin can assign tasks!")
            return

        # Get task details from command arguments
        args = context.args
        if not args:
            await update.message.reply_text(
                "❌ Usage: /assign [employee_names] task [time] [priority] [due_date]\n\n"
                "Example: /assign shameem,rehan Check inventory 30m high tomorrow"
            )
            return

        # Parse command arguments
        employee_names = []
        task_description = ""
        time_minutes = None
        priority = "normal"
        due_date = None

        # Parse employee names (comma-separated list at start)
        if ',' in args[0]:
            employee_names = args[0].split(',')
            args = args[1:]
        else:
            employee_names = [args[0]]
            args = args[1:]

        # Get task description
        if args:
            task_description = args[0]
            args = args[1:]

        # Parse optional time (minutes)
        if args and args[0].isdigit():
            time_minutes = int(args[0])
            args = args[1:]

        # Parse optional priority
        if args and args[0].lower() in ['low', 'normal', 'high']:
            priority = args[0].lower()
            args = args[1:]

        # Parse optional due date
        if args:
            due_date = args[0].lower()

        # Validate task description
        if not task_description:
            await update.message.reply_text("❌ Task description is required!")
            return

        # Get employee chat IDs
        employee_chat_ids = []
        for name in employee_names:
            employee = db.employees.find_one({"name": name.strip()})
            if employee:
                employee_chat_ids.append(employee["chat_id"])
            else:
                await update.message.reply_text(f"❌ Employee '{name}' not found!")
                return

        # Generate unique task ID
        task_id = db.tasks.count_documents({}) + 1

        # Create task data
        task_data = {
            "task_id": task_id,
            "task": task_description,
            "assigned_by": chat_id,
            "assigned_to": employee_chat_ids,
            "assigned_at": datetime.now(),
            "status": "active",
            "priority": priority,
            "due_date": due_date,
            "reminder_interval": time_minutes or 60  # Default to hourly reminders
        }

        # Store task in MongoDB
        db.tasks.insert_one(task_data)

        # Create keyboard with task completion button
        keyboard = [[InlineKeyboardButton("✅ Mark as Done", callback_data=f"taskdone_{task_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Send task notification to each employee
        for emp_chat_id in employee_chat_ids:
            try:
                await context.bot.send_message(
                    chat_id=emp_chat_id,
                    text=f"📝 New Task #{task_id}\n"
                         f"• Description: {task_description}\n"
                         f"• Priority: {priority}\n"
                         f"• Time: {time_minutes or 'Not specified'} minutes\n"
                         f"• Due: {due_date or 'Not specified'}\n\n"
                         f"Assigned by Admin",
                    reply_markup=reply_markup
                )
            except Exception as e:
                logger.error(f"Failed to notify employee {emp_chat_id}: {e}")

        # Send confirmation to admin
        await update.message.reply_text(
            f"✅ Created Task #{task_id}\n"
            f"• Description: {task_description}\n"
            f"• Priority: {priority}\n"
            f"• Time: {time_minutes or 'Not specified'} minutes\n"
            f"• Due: {due_date or 'Not specified'}\n\n"
            f"Assigned to: {', '.join(employee_names)}"
        )

    except Exception as e:
        logger.error(f"Error in assign_task: {e}")
        await update.message.reply_text("❌ An error occurred while creating the task.")

async def tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /tasks command to view and manage tasks"""
    try:
        chat_id = str(update.message.chat_id)
        is_admin = chat_id == YOUR_ID

        # Get task ID if provided
        args = context.args
        task_id = None
        if args:
            try:
                task_id = int(args[0])
            except ValueError:
                await update.message.reply_text("❌ Invalid task ID format!")
                return

        # If task ID is provided, handle completion
        if task_id:
            await handle_task_completion(update, context, task_id, is_admin)
            return

        # Get active tasks
        if is_admin:
            # Admin sees all active tasks
            tasks = list(db.tasks.find({"status": "active"}))
        else:
            # Employee sees their own tasks
            employee = db.employees.find_one({"chat_id": chat_id})
            if not employee:
                await update.message.reply_text("❌ You are not registered as an employee.")
                return
            
            tasks = list(db.tasks.find({
                "status": "active",
                "assigned_to": chat_id
            }))

        if not tasks:
            if is_admin:
                await update.message.reply_text("📊 No active tasks at the moment.")
            else:
                await update.message.reply_text("📊 You have no active tasks at the moment.")
            return

        # Format and send tasks
        for task in tasks:
            message = await format_task_message(task, chat_id)
            
            # Create keyboard with task completion button
            keyboard = [[InlineKeyboardButton("✅ Mark as Done", callback_data=f"taskdone_{task['task_id']}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(message, reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Error in tasks_command: {e}")
        await update.message.reply_text("❌ An error occurred while fetching tasks.")

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
        if not is_admin:
            if chat_id not in task_info.get('assigned_to', []):
                await update.message.reply_text("❌ You can only mark your own tasks as done!")
                return
        
        # Update task status
        updated_task = db.update_task_status(
            task_id=task_id,
            status='completed',
            completed_by=employee_name or 'Admin'
        )
        
        if not updated_task:
            await update.message.reply_text(f"❌ Failed to mark Task #{task_id} as completed!")
            return
        
        # Send confirmation to user
        await update.message.reply_text(
            f"✅ Task #{task_id} marked as completed!\n"
            f"• Task: {task_info['task']}\n"
            f"• Completed by: {employee_name or 'Admin'}\n"
            f"• Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        
        # Notify admin if employee completed the task
        if not is_admin:
            try:
                await context.bot.send_message(
                    chat_id=YOUR_ID,
                    text=f"✅ Task #{task_id} completed by {employee_name}\n"
                         f"• Task: {task_info['task']}\n"
                         f"• Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                )
            except Exception as e:
                logger.error(f"Failed to notify admin: {e}")
        
        # Refresh active tasks for all employees
        if is_admin:
            # Get all employees assigned to this task
            assigned_ids = task_info.get('assigned_to', [])
            for emp_id in assigned_ids:
                try:
                    await send_active_tasks(emp_id, context)
                except Exception as e:
                    logger.error(f"Failed to refresh active tasks for {emp_id}: {e}")

    except Exception as e:
        logger.error(f"Error in handle_task_completion: {e}")
        await update.message.reply_text("❌ Failed to process command. Please try again.")

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
            
            # Get employee name for non-admin users
            employee_name = None
            if chat_id != YOUR_ID:
                employee = db.employees.find_one({"chat_id": chat_id})
                if employee:
                    employee_name = employee.get("name")
            
            # Handle task completion
            await handle_task_completion(update, context, task_id, chat_id == YOUR_ID, employee_name)
            
        elif data == 'cmd_help':
            await help_command(update, context)
            await query.answer()
            
    except Exception as e:
        logger.error(f"Error in handle_button_callback: {e}")
        await query.answer("❌ An error occurred")

async def main():
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
        application.add_handler(CommandHandler("tasks", tasks_command))
        application.add_handler(CommandHandler("done", tasks_command))  # Legacy command
        application.add_handler(CommandHandler("clarify", clarify_command))
        application.add_handler(CommandHandler("list_employees", list_employees_command))
        application.add_handler(CommandHandler("remove_employee", remove_employee_command))
        application.add_handler(CommandHandler("notify", notify_command))
        application.add_handler(CommandHandler("broadcast", broadcast_command))
        application.add_handler(CommandHandler("task", task_command))
        application.add_handler(CommandHandler("inquire", inquire_command))
        application.add_handler(CommandHandler("dbstatus", db_status_command))
        application.add_handler(CommandHandler("dbreconnect", db_reconnect_command))
        application.add_handler(CommandHandler("dbmigrate", db_migrate_command))
        
        # Message handlers
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_media_message))
        
        # Callback query handler
        application.add_handler(CallbackQueryHandler(handle_button_callback))
        
        # Error handler
        application.add_error_handler(error_handler)
        
        # Log all updates for debugging
        application.add_handler(MessageHandler(filters.ALL, log_all_updates))
        
        # Start the bot
        logger.info("Starting bot...")
        await application.start()
        
        # Run the application in polling mode
        await application.run_polling()
        
    except Exception as e:
        logger.error(f"Error in main: {e}")
        raise

if __name__ == '__main__':
    application.run_polling()
