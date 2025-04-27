import logging
import os
import asyncio

# Set up logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

logger.info("Script started successfully!")

# Import Telegram-related modules
try:
    from telegram import Update
    from telegram.ext import (
        Application,
        CommandHandler,
        CallbackQueryHandler,
        MessageHandler,
        filters,
        ContextTypes,
    )
    logger.info("Telegram modules imported successfully!")
except ImportError as e:
    logger.error(f"Failed to import Telegram modules: {str(e)}")
    raise

# Import MongoDB-related modules
try:
    from pymongo import MongoClient
    logger.info("MongoDB modules imported successfully!")
except ImportError as e:
    logger.error(f"Failed to import MongoDB modules: {str(e)}")
    raise

# Load environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
YOUR_ID = os.getenv("YOUR_ID")

logger.info(f"BOT_TOKEN: {BOT_TOKEN[:5]}... (partially hidden)")
logger.info(f"WEBHOOK_URL: {WEBHOOK_URL}")
logger.info(f"YOUR_ID: {YOUR_ID}")

if not BOT_TOKEN:
    logger.error("BOT_TOKEN environment variable not set!")
    raise ValueError("BOT_TOKEN not set")
if not WEBHOOK_URL:
    logger.error("WEBHOOK_URL environment variable not set!")
    raise ValueError("WEBHOOK_URL not set")
if not YOUR_ID:
    logger.error("YOUR_ID environment variable not set!")
    raise ValueError("YOUR_ID not set")

# MongoDB connection
MONGODB_URI = os.getenv("MONGODB_URI")
logger.info(f"MONGODB_URI: {MONGODB_URI}")

db = None
if not MONGODB_URI:
    logger.error("MONGODB_URI environment variable not set!")
else:
    try:
        logger.info("Attempting to connect to MongoDB...")
        client = MongoClient(MONGODB_URI)
        db = client.trichygold
        client.admin.command('ping')
        logger.info("Successfully connected to MongoDB!")
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {str(e)}")
        logger.warning("Proceeding without MongoDB connection. Some features may not work.")

# Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Received /start command from chat_id: {update.message.chat_id}")
    try:
        if db is None:
            await update.message.reply_text("Welcome to TrichyGold Bot! Database is offline, so some features may not work. Use /help to see available commands.")
        else:
            await update.message.reply_text("Welcome to TrichyGold Bot! Use /help to see available commands.")
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        await update.message.reply_text("❌ An error occurred. Please try again.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text(
            "Available commands:\n"
            "/start - Start the bot\n"
            "/help - Show this help message\n"
            "/assign - Assign a task (admin only)\n"
            "/tasks - List tasks\n"
            "/done - Mark a task as done\n"
            "/clarify - Add details to a task (admin only)\n"
            "/list_employees - List employees"
        )
    except Exception as e:
        logger.error(f"Error in help command: {e}")
        await update.message.reply_text("❌ An error occurred. Please try again.")

async def clarify_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chat_id = str(update.message.chat_id)
        if chat_id != YOUR_ID:
            await update.message.reply_text("❌ Only admin can clarify tasks!")
            return

        if db is None:
            await update.message.reply_text("❌ Database is offline. Cannot clarify tasks at this time.")
            return

        args = context.args
        if len(args) < 2:
            await update.message.reply_text(
                "❌ Usage: /clarify task_id details\n\n"
                "Example: /clarify 1 Update the inventory records"
            )
            return

        task_id = int(args[0])
        details = " ".join(args[1:])

        task = db.tasks.find_one({"task_id": task_id})
        if not task:
            await update.message.reply_text(f"❌ Task #{task_id} not found!")
            return

        db.tasks.update_one(
            {"task_id": task_id},
            {"$set": {"clarification": details}}
        )

        await update.message.reply_text(f"✅ Added clarification to Task #{task_id}:\n• {details}")
    except Exception as e:
        logger.error(f"Error in clarify_command: {e}")
        await update.message.reply_text("❌ An error occurred while clarifying the task.")

# Placeholder for other handlers
async def add_employee_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Add employee command not implemented yet.")

async def remove_employee_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Remove employee command not implemented yet.")

async def list_employees_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("List employees command not implemented yet.")

async def add_test_employees_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Add test employees command not implemented yet.")

async def assign_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Assign task command not implemented yet.")

async def tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Tasks command not implemented yet.")

async def handle_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("Button callback not implemented yet.")

async def global_error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")

async def log_all_updates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Received update: {update}")

if __name__ == "__main__":
    logger.info("Entering main block...")
    try:
        # Build the application
        logger.info("Building application...")
        application = Application.builder().token(BOT_TOKEN).build()
        logger.info("Application built successfully!")

        # Set admin ID in bot_data for handlers
        application.bot_data['ADMIN_ID'] = YOUR_ID
        logger.info("Admin ID set in bot_data")

        # Register all handlers
        logger.info("Registering handlers...")
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("test", start))

        # Employee management handlers
        application.add_handler(CommandHandler("add_employee", add_employee_command))
        application.add_handler(CommandHandler("remove_employee", remove_employee_command))
        application.add_handler(CommandHandler("list_employees", list_employees_command))
        application.add_handler(CommandHandler("add_test_employees", add_test_employees_command))
        
        # Main bot commands
        optional_commands = [
            ("assign", "assign_task"),
            ("tasks", "tasks_command"),
            ("done", "tasks_command"),
            ("clarify", "clarify_command"),
            ("list_employees", "list_employees_command")
        ]
        for cmd, handler_name in optional_commands:
            try:
                handler = globals()[handler_name]
                application.add_handler(CommandHandler(cmd, handler))
                logger.info(f"Registered command: /{cmd}")
            except KeyError:
                logger.warning(f"Skipping /{cmd} - handler {handler_name} not found")

        # Button callback handler
        application.add_handler(CallbackQueryHandler(handle_button_callback))
        # Error handler
        application.add_error_handler(global_error_handler)
        # Log all updates for debugging
        application.add_handler(MessageHandler(filters.ALL, log_all_updates), group=0)
        logger.info("All handlers registered successfully!")

        # Webhook setup
        PORT = int(os.getenv("PORT", 8080))
        logger.info(f"Using port: {PORT}")

        logger.info(f"Starting bot in webhook mode at: {WEBHOOK_URL}")
        
        # Start the webhook server
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