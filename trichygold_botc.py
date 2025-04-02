import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
from datetime import datetime, time
import pytz
import logging
from typing import Dict, List, Optional
from quart import Quart, request
import uvicorn
import os

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Get environment variables
BOT_TOKEN = os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN')
YOUR_ID = os.getenv('ADMIN_ID', 'YOUR_ADMIN_ID')

# Bot Configuration
EMPLOYEES = {
    'shameem': '1341853859',
    'rehan': '1475715464',
    
}

# Initialize Bot
application = Application.builder().token(BOT_TOKEN).build()

# Initialize Flask
app = Quart(__name__)

# Global state management
TASKS: Dict[int, dict] = {}  # task_id: task_info
INQUIRIES: Dict[int, dict] = {}  # inquiry_id: inquiry_info
NOTIFICATIONS: Dict[int, dict] = {}  # notification_id: notification_info
CUSTOM_MESSAGES: Dict[int, dict] = {}  # message_id: message_info
CONTEXT = {}
CONCERN_CONTEXT = {}
TASK_STATUS = {}

# Fixed messages for different times
FIXED_MESSAGES = {
    "10:00": "🌅 Good Morning TrichyGold Team!\n\nToday's Focus:\n• Check daily targets\n• Review inventory\n• Plan customer interactions",
    "14:00": "🌞 Afternoon Update Time!\n\nMid-day Checklist:\n• Sales progress\n• Customer feedback\n• Stock updates",
    "18:00": "🌆 Evening Check-in!\n\nEnd-day Tasks:\n• Complete pending work\n• Update records\n• Prepare for tomorrow",
    "21:00": "🌙 Day End Summary!\n\nBefore Closing:\n• Final counts\n• Security check\n• Tomorrow's preparation"
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
        
        # Store task information
        TASKS[task_id] = {
            'id': task_id,
            'task': task,
            'employees': employees,
            'status': 'active',
            'created_at': datetime.now(pytz.timezone('Asia/Dubai')),
            'reminder_interval': minutes,
            'inquiries': [],
            'clarifications': []
        }
        
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
            created_time = TASKS[task_id]['created_at'].strftime('%I:%M %p')
            
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
    """Handle /done command for admin"""
    chat_id = str(update.message.chat_id)
    if chat_id != YOUR_ID:
        await update.message.reply_text("❌ Only admin can use this command!")
        return
    
    args = context.args
    if not args:
        # List all active tasks
        if not TASKS:
            await update.message.reply_text("📝 No active tasks.")
            return
        
        message = "📋 Active Tasks:\n\n"
        for task_id, task_info in TASKS.items():
            if task_info['status'] == 'active':
                message += (
                    f"Task #{task_id}:\n"
                    f"• Assigned to: {', '.join(task_info['employees'])}\n"
                    f"• Task: {task_info['task']}\n"
                    f"• Created: {task_info['created_at'].strftime('%I:%M %p')} (UAE)\n"
                    f"• Reminder: Every {task_info['reminder_interval']} minutes\n\n"
                )
        
        await update.message.reply_text(message)
    else:
        # Mark specific task as done
        try:
            task_id = int(args[0])
            if task_id not in TASKS:
                await update.message.reply_text(f"❌ Task #{task_id} not found!")
                return
            
            task_info = TASKS[task_id]
            if task_info['status'] != 'active':
                await update.message.reply_text(f"❌ Task #{task_id} is already completed!")
                return
            
            # Mark task as completed
            task_info['status'] = 'completed'
            task_info['completed_at'] = datetime.now(pytz.timezone('Asia/Dubai'))
            task_info['completed_by'] = 'admin'
            
            # Notify employees
            for employee in task_info['employees']:
                try:
                    await context.bot.send_message(
                        chat_id=EMPLOYEES[employee],
                        text=f"✅ Task #{task_id} has been marked as completed by admin.\n"
                             f"Task: {task_info['task']}\n"
                             f"Completed at: {task_info['completed_at'].strftime('%I:%M %p')} (UAE)"
                    )
                except Exception as e:
                    logger.error(f"Failed to notify {employee}: {e}")
            
            await update.message.reply_text(f"✅ Task #{task_id} marked as completed!")
            
        except ValueError:
            await update.message.reply_text("❌ Please provide a valid task number!")
        except Exception as e:
            logger.error(f"Error in done_command: {e}")
            await update.message.reply_text("❌ Failed to process command. Please try again.")

async def clarify_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /clarify command for admin to add details to tasks"""
    chat_id = str(update.message.chat_id)
    if chat_id != YOUR_ID:
        await update.message.reply_text("❌ Only admin can use this command!")
        return
    
    try:
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
        
        # Store context for handling the next message
        context.user_data['clarifying_task'] = task_id
        
        await update.message.reply_text(
            f"📝 Send your clarification for Task #{task_id}\n"
            f"You can send:\n"
            f"• Text message\n"
            f"• Voice message\n"
            f"• Files/Photos"
        )
    
    except Exception as e:
        logger.error(f"Error in clarify_command: {e}")
        await update.message.reply_text("❌ Failed to process command. Please try again.")

async def inquire_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /inquire command for employees"""
    chat_id = str(update.message.chat_id)
    employee_name = get_employee_name(chat_id)
    
    if not employee_name:
        await update.message.reply_text("❌ Only registered employees can use this command!")
        return
    
    try:
        args = context.args
        if not args or not args[0].isdigit():
            await update.message.reply_text(
                "❌ Usage: /inquire <task_id>\n"
                "Then send your question as text, voice, or attachment"
            )
            return
        
        task_id = int(args[0])
        if task_id not in TASKS:
            await update.message.reply_text(f"❌ Task #{task_id} not found!")
            return
        
        task_info = TASKS[task_id]
        if employee_name not in task_info['employees']:
            await update.message.reply_text("❌ This task is not assigned to you!")
            return
        
        # Store context for handling the next message
        context.user_data['inquiring_task'] = task_id
        
        await update.message.reply_text(
            f"📝 Send your question about Task #{task_id}\n"
            f"You can send:\n"
            f"• Text message\n"
            f"• Voice message\n"
            f"• Files/Photos"
        )
    
    except Exception as e:
        logger.error(f"Error in inquire_command: {e}")
        await update.message.reply_text("❌ Failed to process command. Please try again.")

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
        if task_id not in TASKS:
            await update.message.reply_text(f"❌ Task #{task_id} not found!")
            return
        
        task_info = TASKS[task_id]
        if employee_name not in task_info['employees']:
            await update.message.reply_text("❌ This task is not assigned to you!")
            return
        
        if task_info['status'] != 'active':
            await update.message.reply_text(f"❌ Task #{task_id} is already completed!")
            return
        
        # Mark task as completed
        task_info['status'] = 'completed'
        task_info['completed_at'] = datetime.now(pytz.timezone('Asia/Dubai'))
        task_info['completed_by'] = employee_name
        
        # Notify admin
        await context.bot.send_message(
            chat_id=YOUR_ID,
            text=f"✅ Task #{task_id} completed by {employee_name}\n"
                 f"Task: {task_info['task']}\n"
                 f"Completed at: {task_info['completed_at'].strftime('%I:%M %p')} (UAE)"
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
    chat_id = str(update.message.chat_id)
    if chat_id != YOUR_ID:
        await update.message.reply_text("❌ Only admin can use this command!")
        return
    
    # Store context for handling the next message
    context.user_data['broadcasting'] = True
    
    await update.message.reply_text(
        "📝 Send your broadcast message\n"
        "All employees will need to acknowledge this message.\n"
        "You can send:\n"
        "• Text message\n"
        "• Voice message\n"
        "• Files/Photos"
    )

# Helper function for scheduled messages
async def send_fixed_message(context: ContextTypes.DEFAULT_TYPE):
    """Send fixed messages at scheduled times"""
    now = datetime.now(pytz.timezone('Asia/Dubai'))
    current_time = now.strftime("%H:%M")
    
    if current_time in FIXED_MESSAGES:
        message = FIXED_MESSAGES[current_time]
        for employee_id in EMPLOYEES.values():
            try:
                await context.bot.send_message(
                    chat_id=employee_id,
                    text=message
                )
            except Exception as e:
                logger.error(f"Failed to send fixed message to {employee_id}: {e}")

async def send_task_reminder(context: ContextTypes.DEFAULT_TYPE):
    """Send reminder for specific task"""
    job = context.job
    task_id = job.data['task_id']
    
    if task_id in TASKS:
        task_info = TASKS[task_id]
        if task_info['status'] == 'active':
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
            job.schedule_removal()

# Setup scheduled messages
def setup_scheduled_messages(application: Application):
    """Setup fixed message schedule"""
    job_queue = application.job_queue
    
    # Convert times to seconds since midnight
    times = {
        "10:00": time(10, 0),  # 10 AM
        "14:00": time(14, 0),  # 2 PM
        "18:00": time(18, 0),  # 6 PM
        "21:00": time(21, 0)   # 9 PM
    }
    
    for t in times.values():
        job_queue.run_daily(send_fixed_message, time=t, timezone=pytz.timezone('Asia/Dubai'))

# Register handlers
def register_handlers(application: Application):
    """Register all command and message handlers"""
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("assign", assign_task))
    application.add_handler(CommandHandler("done", done_command))
    application.add_handler(CommandHandler("clarify", clarify_command))
    application.add_handler(CommandHandler("inquire", inquire_command))
    application.add_handler(CommandHandler("taskdone", taskdone_command))
    application.add_handler(CommandHandler("notify", notify_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    
    # Add message handlers for media and callbacks here
    application.add_handler(MessageHandler(
        filters.PHOTO | filters.VOICE | filters.DOCUMENT | filters.TEXT,
        handle_media_message
    ))
    application.add_handler(CallbackQueryHandler(handle_button_callback))

async def handle_media_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle media messages for clarifications, inquiries, and notifications"""
    chat_id = str(update.message.chat_id)
    
    if 'clarifying_task' in context.user_data:
        await handle_clarification(update, context)
    elif 'inquiring_task' in context.user_data:
        await handle_inquiry(update, context)
    elif 'notifying' in context.user_data:
        await handle_notification(update, context)
    elif 'broadcasting' in context.user_data:
        await handle_broadcast(update, context)

async def handle_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks"""
    query = update.callback_query
    data = query.data
    
    if data.startswith('taskdone_'):
        task_id = int(data.split('_')[1])
        await handle_taskdone_callback(update, context, task_id)
    elif data.startswith('inquire_'):
        task_id = int(data.split('_')[1])
        await handle_inquire_callback(update, context, task_id)
    elif data.startswith('ack_'):
        message_id = int(data.split('_')[1])
        await handle_acknowledgment_callback(update, context, message_id)

# Main function
async def main():
    """Start the bot"""
    # Register handlers
    register_handlers(application)
    
    # Setup scheduled messages
    setup_scheduled_messages(application)
    
    # Start the bot
    await application.initialize()
    await application.start()
    await application.run_polling()

if __name__ == '__main__':
    asyncio.run(main())