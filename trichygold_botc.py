import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
from quart import Quart, request
import uvicorn
import logging
from datetime import datetime, time, timedelta
import aiohttp
import pytz
from fastapi import FastAPI
import hypercorn.asyncio

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot Configuration
BOT_TOKEN = '7358468280:AAGktrhJSHmhHWlW8KmME_ST5P6VQkoj_Vo'
YOUR_ID = '1341853859'  # Madam's ID
SERVICE_URL = 'https://trichygold-bot.onrender.com'
PORT = 8000

# Employee Configuration
EMPLOYEES = {
    'shameem': '1341853859',  # Madam's ID
    'rehan': '1475715464'
}

# Initialize FastAPI and Bot
app = FastAPI()
application = Application.builder().token(BOT_TOKEN).build()

# Dictionary to store active employee chat IDs
ACTIVE_EMPLOYEES = {}

# Global state management
CONTEXT = {}
CONCERN_CONTEXT = {}
TASK_STATUS = {}

# In-memory storage for tasks and concerns
TASKS = {}  # Format: {task_id: {'title': str, 'description': str, 'assigned_to': str, 'status': str, 'created_at': datetime, 'completed_at': None}}
CONCERNS = {}  # Format: {concern_id: {'title': str, 'description': str, 'reported_by': str, 'status': str, 'created_at': datetime, 'resolved_at': None}}

# Update the message system
FIXED_MESSAGES = {
    'morning': "🌅 Good Morning TrichyGold Team!\n\n"
              "📊 Today's Focus:\n"
              "• Check daily sales target\n"
              "• Review inventory status\n"
              "• Plan customer follow-ups\n\n"
              "💪 Let's make today successful!",
    
    'afternoon': "🌇 Good Afternoon TrichyGold Team!\n\n"
                "📈 Mid-day Check:\n"
                "• How are sales going?\n"
                "• Any customer feedback?\n"
                "• Need any support?\n\n"
                "Keep up the great work! 💪",
    
    'evening': "🌙 Good Evening TrichyGold Team!\n\n"
              "📊 End of Day Summary:\n"
              "• Review today's achievements\n"
              "• Plan for tomorrow\n"
              "• Any pending tasks?\n\n"
              "Great job today! 👏",
    
    'night': "🌙 Good Night TrichyGold Team!\n\n"
            "📝 Final Check:\n"
            "• All tasks completed?\n"
            "• Shop properly closed?\n"
            "• Ready for tomorrow?\n\n"
            "Rest well! 🌟"
}

# Custom messages that can be added dynamically
CUSTOM_MESSAGES = {}

# Update the daily messages
DAILY_MESSAGES = [
    "🌅 Good Morning TrichyGold Team!\n\n"
    "📊 Today's Focus:\n"
    "• Check daily sales target\n"
    "• Review inventory status\n"
    "• Plan customer follow-ups\n\n"
    "💪 Let's make today successful!",
    
    "🌇 Good Afternoon TrichyGold Team!\n\n"
    "📈 Mid-day Check:\n"
    "• How are sales going?\n"
    "• Any customer feedback?\n"
    "• Need any support?\n\n"
    "Keep up the great work! 💪"
]

# Add after the global variables
PING_URL = 'https://trichygold-bot.onrender.com/ping'
LAST_PING = datetime.now()

# Helper Functions
def get_current_time():
    """Get current time in IST"""
    ist = pytz.timezone('Asia/Kolkata')
    return datetime.now(ist)

def get_greeting():
    """Get appropriate greeting based on time"""
    current_hour = get_current_time().hour
    if 5 <= current_hour < 12:
        return "Good Morning"
    elif 12 <= current_hour < 17:
        return "Good Afternoon"
    elif 17 <= current_hour < 21:
        return "Good Evening"
    else:
        return "Good Night"

async def send_daily_reminder(chat_id: str, employee_name: str):
    """Send daily reminder to an employee"""
    try:
        # Check if chat exists
        try:
            await application.bot.get_chat(chat_id)
        except Exception as e:
            logger.warning(f"Chat not found for {employee_name}: {str(e)}")
            return

        current_time = get_current_time()
        greeting = get_greeting()
        
        message = (
            f"{greeting} {employee_name}! 👋\n\n"
            "Please provide your daily report using /mydone command."
        )
        
        await application.bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode='HTML'
        )
        logger.info(f"Sent daily reminder to {employee_name}")
    except Exception as e:
        logger.error(f"Error sending daily reminder to {employee_name}: {str(e)}")

async def ping():
    """Ping the service to keep it alive"""
    global LAST_PING
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(PING_URL) as response:
                if response.status == 200:
                    LAST_PING = datetime.now()
                    logger.info("Ping successful")
                else:
                    logger.error(f"Ping failed with status {response.status}")
    except Exception as e:
        logger.error(f"Error during ping: {str(e)}")

# Command Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command"""
    user_id = str(update.effective_user.id)
    chat_id = update.effective_chat.id
    
    if user_id == YOUR_ID:
        await update.message.reply_text(
            "Welcome Madam! 👋\n\n"
            "You can use the following commands:\n"
            "• /assign - Assign a task\n"
            "• /list_tasks - List all tasks\n"
            "• /list_concerns - List all concerns\n"
            "• /add_message - Add a custom message\n"
            "• /remove_message - Remove a custom message\n"
            "• /list_messages - List all messages\n"
            "• /send_message - Send a message to all employees"
        )
    else:
        await update.message.reply_text(
            "Welcome to TrichyGold Bot! 👋\n\n"
            "Please use /register command to register yourself."
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /help command"""
    user_id = str(update.effective_user.id)
    
    if user_id == YOUR_ID:
        await update.message.reply_text(
            "Madam's Commands:\n"
            "• /assign - Assign a task\n"
            "• /list_tasks - List all tasks\n"
            "• /list_concerns - List all concerns\n"
            "• /add_message - Add a custom message\n"
            "• /remove_message - Remove a custom message\n"
            "• /list_messages - List all messages\n"
            "• /send_message - Send a message to all employees"
        )
    else:
        await update.message.reply_text(
            "Employee Commands:\n"
            "• /register - Register yourself\n"
            "• /mydone - Mark your tasks as done\n"
            "• /myconcerns - View your concerns\n"
            "• /add_concern - Add a new concern"
        )

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /register command"""
    user_id = str(update.effective_user.id)
    chat_id = update.effective_chat.id
    
    if user_id in EMPLOYEES.values():
        employee_name = next(name for name, id in EMPLOYEES.items() if id == user_id)
        ACTIVE_EMPLOYEES[employee_name] = chat_id
        await update.message.reply_text(f"Welcome back, {employee_name}! You are already registered.")
    else:
        await update.message.reply_text("❌ You are not authorized to register.")

async def assign(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /assign command"""
    user_id = str(update.effective_user.id)
    
    if user_id != YOUR_ID:
        await update.message.reply_text("❌ Only Madam can assign tasks.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "Please provide the task details.\n"
            "Format: /assign <employee_name> <task_title>"
        )
        return
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "Please provide both employee name and task title.\n"
            "Format: /assign <employee_name> <task_title>"
        )
        return
    
    employee_name = context.args[0].lower()
    task_title = ' '.join(context.args[1:])
    
    if employee_name not in EMPLOYEES:
        await update.message.reply_text(f"❌ Employee '{employee_name}' not found.")
        return
    
    employee_id = EMPLOYEES[employee_name]
    task_id = len(TASKS) + 1
    
    # Create new task
    TASKS[task_id] = {
        'title': task_title,
        'description': '',  # Can be updated later
        'assigned_to': employee_id,
        'status': 'pending',
        'created_at': get_current_time(),
        'completed_at': None
    }
    
    # Send notification to employee
    if employee_name in ACTIVE_EMPLOYEES:
        await application.bot.send_message(
            chat_id=ACTIVE_EMPLOYEES[employee_name],
            text=f"📋 New task assigned:\n{task_title}"
        )
    
    await update.message.reply_text(f"✅ Task assigned to {employee_name}")

async def handle_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /done command"""
    user_id = str(update.effective_user.id)
    
    if user_id not in EMPLOYEES.values():
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return
    
    # Get pending tasks for the user
    pending_tasks = [
        task for task_id, task in TASKS.items()
        if task['assigned_to'] == user_id and task['status'] == 'pending'
    ]
    
    if not pending_tasks:
        await update.message.reply_text("No pending tasks found.")
        return
    
    # Create keyboard with task options
    keyboard = []
    for task in pending_tasks:
        keyboard.append([InlineKeyboardButton(
            f"✅ {task['title']}",
            callback_data=f"complete_task_{task['id']}"
        )])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Select a task to mark as completed:",
        reply_markup=reply_markup
    )

async def handle_task_completion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle task completion callback"""
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    task_id = int(query.data.split('_')[2])
    
    if user_id not in EMPLOYEES.values():
        await query.edit_message_text("❌ You are not authorized to complete this task.")
        return
    
    if task_id not in TASKS:
        await query.edit_message_text("❌ Task not found.")
        return
    
    task = TASKS[task_id]
    if task['assigned_to'] != user_id:
        await query.edit_message_text("❌ This task is not assigned to you.")
        return
    
    # Update task status
    task['status'] = 'completed'
    task['completed_at'] = get_current_time()
    
    await query.edit_message_text(f"✅ Task '{task['title']}' marked as completed!")

async def add_concern(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /add_concern command"""
    user_id = str(update.effective_user.id)
    
    if user_id not in EMPLOYEES.values():
        await update.message.reply_text("❌ You are not authorized to add concerns.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "Please provide the concern details.\n"
            "Format: /add_concern <concern_title>"
        )
        return
    
    concern_title = ' '.join(context.args)
    concern_id = len(CONCERNS) + 1
    
    # Create new concern
    CONCERNS[concern_id] = {
        'title': concern_title,
        'description': '',  # Can be updated later
        'reported_by': user_id,
        'status': 'open',
        'created_at': get_current_time(),
        'resolved_at': None
    }
    
    # Notify Madam
    await application.bot.send_message(
        chat_id=ACTIVE_EMPLOYEES['shameem'],
        text=f"⚠️ New concern reported:\n{concern_title}"
    )
    
    await update.message.reply_text("✅ Concern added successfully!")

async def my_concerns(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /myconcerns command"""
    user_id = str(update.effective_user.id)
    
    if user_id not in EMPLOYEES.values():
        await update.message.reply_text("❌ You are not authorized to view concerns.")
        return
    
    # Get concerns reported by the user
    user_concerns = [
        concern for concern_id, concern in CONCERNS.items()
        if concern['reported_by'] == user_id
    ]
    
    if not user_concerns:
        await update.message.reply_text("No concerns found.")
        return
    
    # Format concerns message
    message = "Your Concerns:\n\n"
    for concern in user_concerns:
        status_emoji = "✅" if concern['status'] == 'resolved' else "⏳"
        message += f"{status_emoji} {concern['title']}\n"
        message += f"Status: {concern['status'].title()}\n"
        message += f"Created: {concern['created_at'].strftime('%Y-%m-%d %H:%M')}\n\n"
    
    await update.message.reply_text(message)

async def resolve_concern(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /resolve_concern command"""
    user_id = str(update.effective_user.id)
    
    if user_id != YOUR_ID:
        await update.message.reply_text("❌ Only Madam can resolve concerns.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "Please provide the concern ID.\n"
            "Format: /resolve_concern <concern_id>"
        )
        return
    
    try:
        concern_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Please provide a valid concern ID.")
        return
    
    if concern_id not in CONCERNS:
        await update.message.reply_text("❌ Concern not found.")
        return
    
    concern = CONCERNS[concern_id]
    concern['status'] = 'resolved'
    concern['resolved_at'] = get_current_time()
    
    # Notify the employee who reported the concern
    reporter_id = concern['reported_by']
    if reporter_id in ACTIVE_EMPLOYEES.values():
        await application.bot.send_message(
            chat_id=ACTIVE_EMPLOYEES[reporter_id],
            text=f"✅ Your concern '{concern['title']}' has been resolved!"
        )
    
    await update.message.reply_text(f"✅ Concern '{concern['title']}' marked as resolved!")

async def list_concerns(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /list_concerns command"""
    user_id = str(update.effective_user.id)
    
    if user_id != YOUR_ID:
        await update.message.reply_text("❌ Only Madam can list all concerns.")
        return
    
    if not CONCERNS:
        await update.message.reply_text("No concerns found.")
        return
    
    # Format concerns message
    message = "All Concerns:\n\n"
    for concern_id, concern in CONCERNS.items():
        status_emoji = "✅" if concern['status'] == 'resolved' else "⏳"
        reporter_name = next(name for name, id in EMPLOYEES.items() if id == concern['reported_by'])
        message += f"{status_emoji} Concern #{concern_id}\n"
        message += f"Title: {concern['title']}\n"
        message += f"Reported by: {reporter_name}\n"
        message += f"Status: {concern['status'].title()}\n"
        message += f"Created: {concern['created_at'].strftime('%Y-%m-%d %H:%M')}\n\n"
    
    await update.message.reply_text(message)

async def add_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /add_message command"""
    user_id = str(update.effective_user.id)
    
    if user_id != YOUR_ID:
        await update.message.reply_text("❌ Only Madam can add messages.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "Please provide the message details.\n"
            "Format: /add_message <message_id> <message_text>"
        )
        return
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "Please provide both message ID and text.\n"
            "Format: /add_message <message_id> <message_text>"
        )
        return
    
    message_id = context.args[0]
    message_text = ' '.join(context.args[1:])
    
    CUSTOM_MESSAGES[message_id] = message_text
    await update.message.reply_text(f"✅ Message '{message_id}' added successfully!")

async def remove_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /remove_message command"""
    user_id = str(update.effective_user.id)
    
    if user_id != YOUR_ID:
        await update.message.reply_text("❌ Only Madam can remove messages.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "Please provide the message ID.\n"
            "Format: /remove_message <message_id>"
        )
        return
    
    message_id = context.args[0]
    
    if message_id in CUSTOM_MESSAGES:
        del CUSTOM_MESSAGES[message_id]
        await update.message.reply_text(f"✅ Message '{message_id}' removed successfully!")
    else:
        await update.message.reply_text(f"❌ Message '{message_id}' not found.")

async def list_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /list_messages command"""
    user_id = str(update.effective_user.id)
    
    if user_id != YOUR_ID:
        await update.message.reply_text("❌ Only Madam can list messages.")
        return
    
    if not CUSTOM_MESSAGES:
        await update.message.reply_text("No custom messages found.")
        return
    
    # Format messages list
    message = "Custom Messages:\n\n"
    for message_id, message_text in CUSTOM_MESSAGES.items():
        message += f"ID: {message_id}\n"
        message += f"Text: {message_text}\n\n"
    
    await update.message.reply_text(message)

async def send_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /send_message command"""
    user_id = str(update.effective_user.id)
    
    if user_id != YOUR_ID:
        await update.message.reply_text("❌ Only Madam can send messages.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "Please provide the message ID.\n"
            "Format: /send_message <message_id>"
        )
        return
    
    message_id = context.args[0]
    
    if message_id not in CUSTOM_MESSAGES:
        await update.message.reply_text(f"❌ Message '{message_id}' not found.")
        return
    
    message_text = CUSTOM_MESSAGES[message_id]
    sent_count = 0
    
    # Send message to all active employees
    for employee_name, chat_id in ACTIVE_EMPLOYEES.items():
        try:
            await application.bot.send_message(
                chat_id=chat_id,
                text=message_text
            )
            sent_count += 1
        except Exception as e:
            logger.error(f"Error sending message to {employee_name}: {str(e)}")
    
    await update.message.reply_text(f"✅ Message sent to {sent_count} employees!")

# FastAPI endpoints
@app.get("/")
async def root():
    return {"status": "TrichyGold Bot is running"}

@app.get("/ping")
async def ping_endpoint():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

# Start both servers
async def start_servers():
    """Start both FastAPI and Telegram bot servers"""
    config = hypercorn.Config()
    config.bind = [f"0.0.0.0:{PORT}"]
    
    await hypercorn.asyncio.serve(app, config)
    await application.run_polling(allowed_updates=Update.ALL_TYPES)

def main():
    """Start the bot."""
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("register", register))
    application.add_handler(CommandHandler("assign", assign))
    application.add_handler(CommandHandler("done", handle_done))
    application.add_handler(CommandHandler("add_concern", add_concern))
    application.add_handler(CommandHandler("myconcerns", my_concerns))
    application.add_handler(CommandHandler("resolve_concern", resolve_concern))
    application.add_handler(CommandHandler("list_concerns", list_concerns))
    application.add_handler(CommandHandler("add_message", add_message))
    application.add_handler(CommandHandler("remove_message", remove_message))
    application.add_handler(CommandHandler("list_messages", list_messages))
    application.add_handler(CommandHandler("send_message", send_message))
    application.add_handler(CommandHandler("ping", ping))
    
    # Add callback query handlers
    application.add_handler(CallbackQueryHandler(handle_task_completion, pattern="^complete_task_"))
    
    # Start the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()