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
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('trichygold_bot.log')
    ]
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
def get_employee_name(chat_id: str) -> Optional[str]:
    for name, eid in EMPLOYEES.items():
        if eid == chat_id:
            return name
    return None

def format_task_message(task: str, minutes: int) -> str:
    return f"📋 New Task Assigned!\n\nTask: {task}\nReminder: Every {minutes} minutes\n\nPlease reply to this message with:\n• Text updates\n• Voice messages\n• Files/documents\n• 'done' when completed."

def create_task_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("Mark as Done ✅", callback_data="done"),
            InlineKeyboardButton("Ask for Clarification ❓", callback_data="clarify")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# Command Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command"""
    chat_id = str(update.message.chat_id)
    user_name = update.message.from_user.first_name
    welcome_message = generate_welcome_message(chat_id, user_name)
    await update.message.reply_text(welcome_message)

def generate_welcome_message(chat_id: str, user_name: str) -> str:
    if chat_id == YOUR_ID:
        return (
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
            return (
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
            return (
                f"👋 Welcome {user_name}!\n\n"
                f"⚠️ You are not registered.\n"
                f"Your Chat ID: {chat_id}\n\n"
                f"Please contact admin to get registered."
            )

async def assign_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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

# Other command handlers (done_command, clarify_command, list_employees_command, notify_command, handle_media_message, handle_button_callback, taskdone_command, broadcast_command, mytasks_command, inquire_command, handle_inquiry) would be defined similarly with improved error handling and logging

# Helper function for scheduled messages
async def send_fixed_message(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send fixed message to all employees"""
    try:
        time_of_day = context.job.data['time_of_day']
        message = FIXED_MESSAGES[time_of_day]
        
        # Send to all employees
        for employee_name, chat_id in EMPLOYEES.items():
            try:
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
                except aiohttp.ClientError as e:
                    logger.error(f"Network error in ping: {e}")
                    await asyncio.sleep(5)  # Shorter sleep before retrying
                except Exception as e:
                    logger.error(f"Unexpected error in ping: {e}")
                    await asyncio.sleep(60)  # Still wait even if there's an error
    except Exception as e:
        logger.error(f"Fatal error in ping: {e}")

@app.route('/')
async def health_check():
    return "Bot is running", 200

@app.route('/webhook', methods=['POST'])
async def webhook():
    data = await request.get_json()
    update = Update.de_json(data, application.bot)
    if update:
        await application.process_update(update)
    return "OK", 200

def main() -> None:
    """Start the bot."""
    try:
        # Create the Application and pass it your bot's token.
        application = Application.builder().token(BOT_TOKEN).build()

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
        webhook_url = f"https://{os.getenv('RENDER_SERVICE_URL', 'localhost')}/webhook"
        await application.bot.set_webhook(webhook_url)
        
        # Start the webhook server
        config = uvicorn.Config(
            app=app,
            host="0.0.0.0",
            port=8080,
            loop="asyncio"
        )
        server = uvicorn.Server(config)
        await server.serve()
    except Exception as e:
        logger.error(f"Fatal error in main: {e}")
        raise

if __name__ == '__main__':
    asyncio.run(main())