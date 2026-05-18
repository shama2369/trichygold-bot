from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from datetime import datetime
import logging
import os
import traceback
from typing import Optional

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

def _normalize_webhook_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    url = url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        url = f"https://{url}"
    if not url.rstrip("/").endswith("/webhook"):
        url = url.rstrip("/") + "/webhook"
    return url


WEBHOOK_URL = _normalize_webhook_url(os.getenv("WEBHOOK_URL"))
if not WEBHOOK_URL:
    logger.error("WEBHOOK_URL environment variable not set!")
else:
    logger.info("WEBHOOK_URL is set for Railway webhook mode")

# Initialize database and bot
from database import db, get_mongodb_uri

if not get_mongodb_uri():
    logger.error(
        "MONGODB_URI not set or invalid — use full string: mongodb+srv://user:pass@cluster.mongodb.net/..."
    )
elif not db.ensure_ready():
    logger.error("MongoDB client failed to connect — check MONGODB_URI and Atlas network access")
from employee_handlers import add_employee_command, remove_employee_command, list_employees_command
from test_employees import add_test_employees_command
from button_handlers import handle_button_callback as button_handlers_callback
from assign_parser import parse_assign_args, ASSIGN_USAGE

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

async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors and send admin notifications"""
    logger.error("Exception while handling update:", exc_info=context.error)
    
    if YOUR_ID:
        tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
        tb_string = "".join(tb_list)[:3000]  # Truncate to avoid hitting message limits
        
        try:
            await context.bot.send_message(
                chat_id=YOUR_ID,
                text=f"⚠️ Bot Crash ⚠️\n\n"
                     f"Update: {update}\n\n"
                     f"Error: {context.error}\n\n"
                     f"Traceback:\n<pre>{tb_string}</pre>",
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Failed to send error notification: {e}")

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
            [InlineKeyboardButton("📊 All Active Tasks", callback_data="cmd_tasks")],
            [InlineKeyboardButton("❓ Help", callback_data="cmd_help")]
        ]
    else:
        # Check if this is a registered employee
        employee_name = None
        if db.ensure_ready():
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

def _chat_id_from_update(update: Update) -> str:
    if update.callback_query:
        return str(update.callback_query.from_user.id)
    if update.message:
        return str(update.message.chat_id)
    if update.effective_user:
        return str(update.effective_user.id)
    raise ValueError("Cannot determine chat id from update")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /help is issued."""
    chat_id = _chat_id_from_update(update)
    
    # Different help message for admin vs employees
    if chat_id == YOUR_ID:
        help_text = r"""
🔑 *Admin Commands*

/assign - Assign tasks to employees
Format: /assign employee1,employee2 <task words> [36m] [p:low] [due:tomorrow]

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
            [InlineKeyboardButton("📊 All Active Tasks", callback_data="cmd_tasks")]
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
    target = update.effective_message
    if not target:
        return
    await target.reply_text(
        help_text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN,
    )

# Command Handlers
async def assign_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /assign command for task assignment"""
    try:
        chat_id = str(update.message.chat_id)
        if chat_id != YOUR_ID:
            await update.message.reply_text("❌ Only admin can assign tasks!")
            return

        args = context.args
        if not args:
            await update.message.reply_text(ASSIGN_USAGE, parse_mode=ParseMode.MARKDOWN)
            return

        if not db.ensure_ready():
            await update.message.reply_text("❌ Database not connected. Check MONGODB_URI on Railway.")
            return

        try:
            employee_names, task_description, time_minutes, priority, due_date = parse_assign_args(
                list(args)
            )
        except ValueError as e:
            await update.message.reply_text(f"❌ {e}\n\n{ASSIGN_USAGE}", parse_mode=ParseMode.MARKDOWN)
            return

        all_employees = list(db.employees.find())
        available = {emp['name'].lower(): emp for emp in all_employees}
        employee_chat_ids = []
        for name in employee_names:
            emp = available.get(name.lower())
            if not emp:
                known = ', '.join(sorted(available.keys())) or '(none)'
                await update.message.reply_text(
                    f"❌ Employee '{name}' not found.\nAvailable: {known}"
                )
                return
            employee_chat_ids.append(emp['chat_id'])

        highest = db.tasks.find_one(sort=[('task_id', -1)])
        task_id = 1 if not highest else highest['task_id'] + 1
        assigned_at = datetime.now()
        formatted_assigned = assigned_at.strftime('%Y-%m-%d %H:%M')

        task_data = {
            "task_id": task_id,
            "task": task_description,
            "employees": employee_names,
            "assigned_by": chat_id,
            "assigned_to": employee_chat_ids,
            "assigned_at": assigned_at,
            "assigned_date": formatted_assigned,
            "status": "active",
            "priority": priority,
            "due_date": due_date,
            "reminder_interval": time_minutes,
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
                         f"• Reminder: every {time_minutes} minutes\n"
                         f"• Due: {due_date or 'Not specified'}\n\n"
                         f"Assigned by Admin",
                    reply_markup=reply_markup
                )
            except Exception as e:
                logger.error(f"Failed to notify employee {emp_chat_id}: {e}")

        priority_icon = (
            "🔴" if priority == "high" else "🟡" if priority == "medium" else "🟢"
        )
        await update.message.reply_text(
            f"✅ Created Task #{task_id}\n"
            f"• Description: {task_description}\n"
            f"• Priority: {priority_icon} {priority}\n"
            f"• Reminder: every {time_minutes} minutes\n"
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
    """Handle task completion for both admin and employees. Handles both command and callback contexts safely."""
    try:
        # Determine chat_id and message object depending on context
        if hasattr(update, 'message') and update.message is not None:
            chat_id = str(update.message.chat_id)
            message_obj = update.message
        elif hasattr(update, 'callback_query') and update.callback_query is not None:
            if update.callback_query.message is not None:
                chat_id = str(update.callback_query.message.chat_id)
                message_obj = update.callback_query.message
            else:
                logger.error("Callback query has no associated message (possibly message was deleted or callback is stale).")
                await update.callback_query.answer("❌ This button is no longer valid or the message was deleted.")
                return
        else:
            logger.error("No message or callback_query.message found in update!")
            return

        # Get task from database
        task_info = db.get_task(task_id)
        if not task_info:
            await message_obj.reply_text(f"❌ Task #{task_id} not found!")
            return

        # Allow admin to mark any task as done, but employees can only mark their own tasks
        if not is_admin:
            if chat_id not in task_info.get('assigned_to', []):
                await message_obj.reply_text("❌ You can only mark your own tasks as done!")
                return

        # Update task status
        updated_task = db.update_task_status(
            task_id=task_id,
            status='completed',
            completed_by=employee_name or 'Admin'
        )
        if not updated_task:
            await message_obj.reply_text(f"❌ Failed to mark Task #{task_id} as completed!")
            return

        # Send confirmation to user
        await message_obj.reply_text(
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
            assigned_ids = task_info.get('assigned_to', [])
            for emp_id in assigned_ids:
                try:
                    await send_active_tasks(emp_id, context)
                except Exception as e:
                    logger.error(f"Failed to refresh active tasks for {emp_id}: {e}")

    except Exception as e:
        logger.error(f"Error in handle_task_completion: {e}")
        # Try to reply to the user in the safest way
        try:
            if 'message_obj' in locals():
                await message_obj.reply_text("❌ Failed to process command. Please try again.")
            elif hasattr(update, 'callback_query') and update.callback_query is not None:
                await update.callback_query.answer("❌ Failed to process command.")
        except Exception as ex:
            logger.error(f"Failed to send error message: {ex}")


async def handle_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard presses (delegates to button_handlers)."""
    await button_handlers_callback(update, context)

def register_handlers(app: Application) -> None:
    """Register all bot command and callback handlers."""
    for cmd, handler in (
        ("start", start),
        ("help", help_command),
        ("test", test_command),
        ("add_employee", add_employee_command),
        ("remove_employee", remove_employee_command),
        ("list_employees", list_employees_command),
        ("add_test_employees", add_test_employees_command),
        ("assign", assign_task),
        ("tasks", tasks_command),
        ("done", tasks_command),
    ):
        app.add_handler(CommandHandler(cmd, handler))
        logger.info(f"Registered command: /{cmd}")

    app.add_handler(CallbackQueryHandler(handle_button_callback))
    app.add_error_handler(global_error_handler)

    if os.getenv("DEBUG_UPDATES", "").lower() in ("1", "true", "yes"):
        app.add_handler(MessageHandler(filters.ALL, log_all_updates), group=0)
        logger.info("DEBUG_UPDATES enabled — logging all incoming updates")

async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Simple test command to verify bot responsiveness"""
    try:
        await update.message.reply_text("✅ Bot is operational!")
        logger.info("Test command executed successfully")
    except Exception as e:
        logger.error(f"Test command failed: {e}")
        raise

if __name__ == '__main__':
    try:
        application = Application.builder().token(BOT_TOKEN).build()
        application.bot_data['ADMIN_ID'] = YOUR_ID
        register_handlers(application)
        logger.info("All handlers registered successfully!")

        # Webhook setup
        PORT = int(os.getenv("PORT", 8080))
        logger.info(f"Using port: {PORT}")

        logger.info(f"Starting bot in webhook mode at: {WEBHOOK_URL}")
        
        # Start the webhook server (no middleware needed)
        logger.info(f"Starting webhook server on port {PORT}...")
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path="/webhook",
            webhook_url=WEBHOOK_URL
        )
        logger.info("Webhook server started successfully!")
    except Exception as e:
        logger.error(f"Error in main block: {str(e)}")
        raise
    finally:
        logger.info("Application is shutting down...")