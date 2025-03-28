import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
from quart import Quart, request
import uvicorn
import logging
from datetime import datetime, time, timedelta
import aiohttp
import os

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot Configuration
BOT_TOKEN = '7358468280:AAGktrhJSHmhHWlW8KmME_ST5P6VQkoj_Vo'
YOUR_ID = '1341853859'
EMPLOYEES = {
    'shameem': '1341853859',
    'rehan': '1475715464',
    'employee3': 'CHAT_ID_3',
    'employee4': 'CHAT_ID_4',
    'employee5': 'CHAT_ID_5',
    'employee6': 'CHAT_ID_6',
    'employee7': 'CHAT_ID_7',
    'employee8': 'CHAT_ID_8',
    'employee9': 'CHAT_ID_9',
    'employee10': 'CHAT_ID_10',
    'employee11': 'CHAT_ID_11',
    'employee12': 'CHAT_ID_12',
    'employee13': 'CHAT_ID_13',
}

# Initialize Flask and Bot
app = Quart(__name__)
application = Application.builder().token(BOT_TOKEN).build()

# Global state management
CONTEXT = {}
CONCERN_CONTEXT = {}
TASK_STATUS = {}

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
PING_URL = os.getenv('PING_URL', 'https://your-ping-url.com')  # Replace with your actual ping URL
LAST_PING = datetime.now()

# Helper Functions
def get_employee_name(chat_id):
    for name, eid in EMPLOYEES.items():
        if eid == str(chat_id):
            return name
    return None

def format_task_message(task: str, minutes: int) -> str:
    return (
        f"📝 New Task Assigned!\n\n"
        f"Task: {task}\n"
        f"Reminders every {minutes} minutes\n\n"
        f"To respond:\n"
        f"• Use /concern to raise any concerns\n"
        f"• Use /mydone to mark task as completed"
    )

def create_task_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("📝 Mark as Done", callback_data="mydone"),
            InlineKeyboardButton("❓ Raise Concern", callback_data="concern")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# Command Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    employee_name = get_employee_name(chat_id)
    
    if chat_id == YOUR_ID:
        welcome_message = (
            "👋 Welcome to TrichyGold Task Manager!\n\n"
            "📚 Available Commands:\n"
            "/assign <employee1,employee2,...> <task> [minutes]\n"
            "  Example: /assign rehan,shameem check inventory 30\n\n"
            "/list - View all active tasks\n"
            "/done - Mark a task as completed\n"
            "/clarify - Send clarification for a task\n"
            "/concerns - View all concerns\n"
            "/help - Show detailed help message"
        )
    else:
        welcome_message = (
            f"👋 Welcome {employee_name}!\n\n"
            "📚 Available Commands:\n"
            "/mydone - Mark your task as completed\n"
            "  Example: /mydone 1\n\n"
            "/concern - Raise a concern about a task\n"
            "  Example: /concern 1 Need more materials\n\n"
            "To respond to tasks:\n"
            "• Use /mydone to mark tasks as completed\n"
            "• Use /concern to raise concerns\n"
            "/help - Show detailed help message"
        )
    
    await update.message.reply_text(welcome_message)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    if chat_id == YOUR_ID:
        help_text = (
            "📚 Admin Commands:\n\n"
            "/assign <employee1,employee2,...> <task> [minutes]\n"
            "  Example: /assign rehan,shameem check inventory 30\n\n"
            "/list - View all active tasks\n"
            "/done - Mark a task as completed\n"
            "/clarify - Send clarification for a task\n"
            "/concerns - View all concerns\n\n"
            "📝 Message Management:\n"
            "/viewmessages - View all messages\n"
            "/addmessage - Add new custom message\n"
            "/removemessage - Remove custom message\n"
            "/sendmessage - Send a message to all\n\n"
            "To clarify tasks:\n"
            "• Use /clarify to select a task\n"
            "• Then send voice/photo"
        )
    else:
        help_text = (
            "📚 Employee Commands:\n\n"
            "/mydone - Mark your task as completed\n"
            "  Example: /mydone 1\n\n"
            "/concern - Raise a concern about a task\n"
            "  Example: /concern 1 Need more materials\n\n"
            "To respond to tasks:\n"
            "• Use /mydone to mark tasks as completed\n"
            "• Use /concern to raise concerns\n\n"
            "To raise concerns:\n"
            "• Use /concern to see your tasks\n"
            "• Then use /concern <task_number> <your concern>\n"
            "• Or send voice/photo after selecting task"
        )
    
    await update.message.reply_text(help_text)

async def assign_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.chat_id) != YOUR_ID:
        await update.message.reply_text("❌ Only Madam can assign tasks!")
        return
    
    try:
        args = context.args
        if len(args) < 2:
            raise ValueError("Not enough arguments")
        
        # Handle multiple employees
        employees = [emp.strip().lower() for emp in args[0].split(',')]
        invalid_employees = [emp for emp in employees if emp not in EMPLOYEES]
        
        if invalid_employees:
            await update.message.reply_text(
                f"❌ Invalid employee(s): {', '.join(invalid_employees)}\n\n"
                f"Available employees: {', '.join(EMPLOYEES.keys())}"
            )
            return
        
        # Parse task and minutes
        if len(args) > 2 and args[-1].isdigit():
            task = ' '.join(args[1:-1])
            minutes = int(args[-1])
        else:
            task = ' '.join(args[1:])
            minutes = 60
        
        # Send task to each employee
        confirmation_messages = []
        for employee in employees:
            chat_id = EMPLOYEES[employee]
            msg = await context.bot.send_message(
                chat_id=chat_id,
                text=format_task_message(task, minutes),
                reply_markup=create_task_keyboard()
            )
            
            # Set up reminders for each employee
            if context.job_queue is None:
                logger.error("Job queue is None!")
                await update.message.reply_text("❌ Error: Reminder scheduling failed.")
                return
            
            job = context.job_queue.run_repeating(
                send_reminder,
                interval=minutes * 60,
                first=minutes * 60,
                data={'chat_id': chat_id, 'task': task}
            )
            
            # Store task information for each employee
            confirmation = await update.message.reply_text(
                f"✅ Task assigned to {employee}:\n{task}\n"
                f"Reminders every {minutes} minutes"
            )
            
            CONTEXT[confirmation.message_id] = {
                'employee': employee,
                'task': task,
                'chat_id': chat_id,
                'task_msg_id': msg.message_id,
                'job': job,
                'status': 'active',
                'assigned_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'team_task': len(employees) > 1,
                'team_members': employees
            }
            
            confirmation_messages.append(confirmation.message_id)
            logger.info(f"Task assigned to {employee}: {task} (reminders every {minutes} minutes)")
        
        # Send team task notification if multiple employees
        if len(employees) > 1:
            team_message = (
                f"👥 Team Task Assigned!\n\n"
                f"Task: {task}\n"
                f"Team Members: {', '.join(employees)}\n"
                f"Reminders every {minutes} minutes\n\n"
                f"Please coordinate with your team members."
            )
            await update.message.reply_text(team_message)
        
    except ValueError as e:
        await update.message.reply_text(
            "❌ Invalid command format.\n\n"
            "Usage: /assign <employee1,employee2,...> <task> [minutes]\n"
            "Example: /assign rehan,shameem check inventory 30"
        )

async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.chat_id) != YOUR_ID:
        await update.message.reply_text("❌ Only Madam can view all tasks!")
        return
    
    if not CONTEXT:
        await update.message.reply_text("📝 No active tasks.")
        return
    
    task_list = "📋 Active Tasks:\n\n"
    for msg_id, task_info in CONTEXT.items():
        task_list += (
            f"👤 {task_info['employee']}\n"
            f"📝 {task_info['task']}\n"
            f"⏰ Assigned: {task_info['assigned_at']}\n"
            f"📊 Status: {task_info['status']}\n\n"
        )
    
    await update.message.reply_text(task_list)

async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.data['chat_id']
    task = job.data['task']
    
    reminder_text = (
        f"⏰ Reminder!\n\n"
        f"Task: {task}\n"
        f"Please update your progress or mark as done."
    )
    
    await context.bot.send_message(
        chat_id=chat_id,
        text=reminder_text,
        reply_markup=create_task_keyboard()
    )

async def concern(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    if chat_id == YOUR_ID:
        await update.message.reply_text("Please use /concerns to view concerns.")
        return
    
    # Check if employee has any active tasks
    employee = None
    for task_info in CONTEXT.values():
        if str(task_info['chat_id']) == chat_id:
            employee = task_info['employee']
            break
    
    if not employee:
        await update.message.reply_text("You don't have any active tasks to raise concerns about.")
        return
    
    # Show active tasks for this employee
    task_list = "Your Active Tasks:\n\n"
    employee_tasks = []
    for idx, (msg_id, task_info) in enumerate(CONTEXT.items(), 1):
        if str(task_info['chat_id']) == chat_id:
            task_list += f"{idx}. 📝 {task_info['task']}\n\n"
            employee_tasks.append((msg_id, task_info))
    
    if not employee_tasks:
        await update.message.reply_text("You don't have any active tasks to raise concerns about.")
        return
    
    task_list += "\nTo raise a concern:\nUsage: /concern <task_number> <your concern>\nExample: /concern 1 Need more materials"
    
    # Store tasks for this employee
    context.user_data['employee_tasks'] = employee_tasks
    
    await update.message.reply_text(task_list)

async def handle_concern_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    if chat_id == YOUR_ID:
        return
    
    # Check if we're in concern mode
    if 'concern_task' in context.user_data:
        task_info = context.user_data['concern_task']
        employee = task_info['employee']
        task = task_info['task']
        
        # Handle different types of media
        if update.message.voice:
            await context.bot.send_voice(
                chat_id=YOUR_ID,
                voice=update.message.voice.file_id,
                caption=f"Voice concern from {employee} for task: {task}"
            )
        elif update.message.photo:
            await context.bot.send_photo(
                chat_id=YOUR_ID,
                photo=update.message.photo[-1].file_id,
                caption=f"Photo concern from {employee} for task: {task}"
            )
        elif update.message.document:
            await context.bot.send_document(
                chat_id=YOUR_ID,
                document=update.message.document.file_id,
                caption=f"Document concern from {employee} for task: {task}"
            )
        
        await update.message.reply_text("Your concern has been sent to Madam.")
        del context.user_data['concern_task']
        return
    
    # Handle text concerns
    if update.message.text and update.message.text.startswith('/concern'):
        args = update.message.text.split(maxsplit=2)
        if len(args) < 3:
            await update.message.reply_text("Please use: /concern <task_number> <your concern>")
            return
        
        try:
            task_number = int(args[1])
            concern_text = args[2]
            
            if 'employee_tasks' not in context.user_data:
                await update.message.reply_text("Please use /concern first to see your tasks.")
                return
            
            employee_tasks = context.user_data['employee_tasks']
            if task_number < 1 or task_number > len(employee_tasks):
                await update.message.reply_text(
                    f"Invalid task number. Please use a number between 1 and {len(employee_tasks)}."
                )
                return
            
            # Get the task at the specified number
            boss_msg_id, task_info = employee_tasks[task_number - 1]
            
            # Send the concern to Madam
            await context.bot.send_message(
                chat_id=YOUR_ID,
                text=f"⚠️ Concern from {task_info['employee']}:\n\nTask: {task_info['task']}\nConcern: {concern_text}"
            )
            
            await update.message.reply_text("Your concern has been sent to Madam.")
            
        except ValueError:
            await update.message.reply_text(
                "Please use a number to specify which task you're concerned about.\n"
                "Example: /concern 1 Need more materials"
            )
        return
    
    await update.message.reply_text("Please use /concern to select a task first.")

async def clarify_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    if chat_id != YOUR_ID:
        await update.message.reply_text("Only Madam can use /clarify!")
        return
    
    args = context.args
    if not args:
        # Show all active tasks with numbers
        if not CONTEXT:
            await update.message.reply_text("No active tasks.")
            return
        
        task_list = "Active Tasks:\n\n"
        for idx, (msg_id, task_info) in enumerate(CONTEXT.items(), 1):
            task_list += f"{idx}. 👤 {task_info['employee']}\n📝 {task_info['task']}\n\n"
        
        await update.message.reply_text(
            task_list + "\nTo send clarification:\n"
            "Usage: /clarify <task_number>\n"
            "Example: /clarify 1"
        )
        return
    
    try:
        task_number = int(args[0])
        if task_number < 1 or task_number > len(CONTEXT):
            await update.message.reply_text(
                f"Invalid task number. Please use a number between 1 and {len(CONTEXT)}."
            )
            return
        
        # Get the task at the specified number
        task_items = list(CONTEXT.items())
        boss_msg_id, task_info = task_items[task_number - 1]
        
        # Store the task info for the next media message
        context.user_data['clarify_task'] = task_info
        
        await update.message.reply_text(
            f"Selected task for {task_info['employee']}: {task_info['task']}\n\n"
            "Now send your voice message or photo for clarification."
        )
            
    except ValueError:
        await update.message.reply_text(
            "Please use a number to specify which task to clarify.\n"
            "Example: /clarify 1"
        )

async def handle_boss_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    if chat_id != YOUR_ID:
        return
    
    # Check if we're in clarification mode
    if 'clarify_task' in context.user_data:
        task_info = context.user_data['clarify_task']
        employee = task_info['employee']
        task = task_info['task']
        
        # Forward the media to the employee
        if update.message.voice:
            await context.bot.send_voice(
                chat_id=EMPLOYEES[employee],
                voice=update.message.voice.file_id,
                caption=f"Voice clarification for task: {task}"
            )
        elif update.message.photo:
            await context.bot.send_photo(
                chat_id=EMPLOYEES[employee],
                photo=update.message.photo[-1].file_id,
                caption=f"Image clarification for task: {task}"
            )
        
        await update.message.reply_text(f"Sent clarification to {employee}")
        del context.user_data['clarify_task']
        return
    
    await update.message.reply_text("Please use /clarify to select a task first.")

async def handle_employee_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    if chat_id not in EMPLOYEES.values() or not update.message.reply_to_message:
        return
    
    reply_msg_id = update.message.reply_to_message.message_id
    
    for boss_msg_id, task_info in list(CONTEXT.items()):
        if task_info['task_msg_id'] == reply_msg_id and task_info['chat_id'] == chat_id:
            employee = task_info['employee']
            task = task_info['task']
            
            if update.message.text and update.message.text.lower() == 'done':
                await context.bot.send_message(
                    chat_id=YOUR_ID,
                    text=f"✅ {employee} completed task: {task}"
                )
                if task_info['job']:
                    task_info['job'].schedule_removal()
                task_info['status'] = 'completed'
                task_info['completed_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                await update.message.reply_text("✅ Task marked as completed!")
            
            elif update.message.text:
                await context.bot.send_message(
                    chat_id=YOUR_ID,
                    text=f"📝 Update from {employee} on '{task}':\n{update.message.text}"
                )
                await update.message.reply_text("✅ Update sent to Madam.")
            
            elif update.message.document:
                file_id = update.message.document.file_id
                await context.bot.send_document(
                    chat_id=YOUR_ID,
                    document=file_id,
                    caption=f"📝 File from {employee} on '{task}'"
                )
                await update.message.reply_text("✅ File sent to Madam.")
            
            elif update.message.voice:
                voice_id = update.message.voice.file_id
                await context.bot.send_voice(
                    chat_id=YOUR_ID,
                    voice=voice_id,
                    caption=f"📝 Voice update from {employee} on '{task}'"
                )
                await update.message.reply_text("✅ Voice message sent to Madam.")
            return

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "mydone":
        # Trigger /mydone command
        await query.message.reply_text("/mydone")
    elif query.data == "concern":
        # Trigger /concern command
        await query.message.reply_text("/concern")
    elif query.data == "done":
        # Trigger /done command
        await query.message.reply_text("/done")
    elif query.data == "clarify":
        # Trigger /clarify command
        await query.message.reply_text("/clarify")

async def done_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    if chat_id != YOUR_ID:
        await update.message.reply_text("Only Madam can use /done!")
        return
    
    args = context.args
    if not args:
        # Show all active tasks with numbers
        if not CONTEXT:
            await update.message.reply_text("No active tasks.")
            return
        
        task_list = "Active Tasks:\n\n"
        for idx, (msg_id, task_info) in enumerate(CONTEXT.items(), 1):
            task_list += f"{idx}. 👤 {task_info['employee']}\n📝 {task_info['task']}\n\n"
        
        await update.message.reply_text(
            task_list + "\nTo mark a task as done:\n"
            "Usage: /done <task_number>\n"
            "Example: /done 1"
        )
        return
    
    try:
        task_number = int(args[0])
        if task_number < 1 or task_number > len(CONTEXT):
            await update.message.reply_text(
                f"Invalid task number. Please use a number between 1 and {len(CONTEXT)}."
            )
            return
        
        # Get the task at the specified number
        task_items = list(CONTEXT.items())
        boss_msg_id, task_info = task_items[task_number - 1]
        
        # Mark the task as done
        employee = task_info['employee']
        task = task_info['task']
        await context.bot.send_message(
            chat_id=YOUR_ID,
            text=f"✅ Task marked as completed for {employee}: {task}"
        )
        if task_info['job']:
            task_info['job'].schedule_removal()  # Stop reminders on done
        del CONTEXT[boss_msg_id]
        
        # Show remaining tasks
        if CONTEXT:
            task_list = "Remaining Active Tasks:\n\n"
            for idx, (msg_id, task_info) in enumerate(CONTEXT.items(), 1):
                task_list += f"{idx}. 👤 {task_info['employee']}\n📝 {task_info['task']}\n\n"
            await update.message.reply_text(task_list)
        else:
            await update.message.reply_text("All tasks have been completed.")
            
    except ValueError:
        await update.message.reply_text(
            "Please use a number to specify which task to mark as done.\n"
            "Example: /done 1"
        )

async def mydone_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    if chat_id == YOUR_ID:
        await update.message.reply_text("Please use /done to mark tasks as completed.")
        return
    
    # Check if employee has any active tasks
    employee = None
    for task_info in CONTEXT.values():
        if str(task_info['chat_id']) == chat_id:
            employee = task_info['employee']
            break
    
    if not employee:
        await update.message.reply_text("You don't have any active tasks to mark as done.")
        return
    
    # Show active tasks for this employee
    task_list = "Your Active Tasks:\n\n"
    employee_tasks = []
    for idx, (msg_id, task_info) in enumerate(CONTEXT.items(), 1):
        if str(task_info['chat_id']) == chat_id:
            task_list += f"{idx}. 📝 {task_info['task']}\n\n"
            employee_tasks.append((msg_id, task_info))
    
    if not employee_tasks:
        await update.message.reply_text("You don't have any active tasks to mark as done.")
        return
    
    task_list += "\nTo mark a task as done:\nUsage: /mydone <task_number>\nExample: /mydone 1"
    
    # Store tasks for this employee
    context.user_data['employee_tasks'] = employee_tasks
    
    await update.message.reply_text(task_list)

async def handle_mydone_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    if chat_id == YOUR_ID:
        return
    
    # Handle text command
    if update.message.text and update.message.text.startswith('/mydone'):
        args = update.message.text.split(maxsplit=1)
        if len(args) < 2:
            await update.message.reply_text("Please use: /mydone <task_number>")
            return
        
        try:
            task_number = int(args[1])
            
            if 'employee_tasks' not in context.user_data:
                await update.message.reply_text("Please use /mydone first to see your tasks.")
                return
            
            employee_tasks = context.user_data['employee_tasks']
            if task_number < 1 or task_number > len(employee_tasks):
                await update.message.reply_text(
                    f"Invalid task number. Please use a number between 1 and {len(employee_tasks)}."
                )
                return
            
            # Get the task at the specified number
            boss_msg_id, task_info = employee_tasks[task_number - 1]
            
            # Mark the task as done
            employee = task_info['employee']
            task = task_info['task']
            await context.bot.send_message(
                chat_id=YOUR_ID,
                text=f"✅ {employee} completed task: {task}"
            )
            if task_info['job']:
                task_info['job'].schedule_removal()
            task_info['status'] = 'completed'
            task_info['completed_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            del CONTEXT[boss_msg_id]
            
            await update.message.reply_text("✅ Task marked as completed!")
            
            # Show remaining tasks
            remaining_tasks = [t for t in employee_tasks if t[0] != boss_msg_id]
            if remaining_tasks:
                task_list = "Your Remaining Tasks:\n\n"
                for idx, (msg_id, task_info) in enumerate(remaining_tasks, 1):
                    task_list += f"{idx}. 📝 {task_info['task']}\n\n"
                await update.message.reply_text(task_list)
            
        except ValueError:
            await update.message.reply_text(
                "Please use a number to specify which task to mark as done.\n"
                "Example: /mydone 1"
            )
        return
    
    await update.message.reply_text("Please use /mydone to select a task first.")

# Add message management commands
async def add_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.chat_id) != YOUR_ID:
        await update.message.reply_text("❌ Only Madam can add messages!")
        return
    
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "❌ Invalid command format.\n\n"
            "Usage: /addmessage <name> <your message>\n"
            "Example: /addmessage special Good morning team!"
        )
        return
    
    name = args[0].lower()
    message = ' '.join(args[1:])
    
    if name in FIXED_MESSAGES:
        await update.message.reply_text("❌ This name is reserved for fixed messages. Please use a different name.")
        return
    
    CUSTOM_MESSAGES[name] = message
    await update.message.reply_text(
        f"✅ Custom message '{name}' added successfully!\n\n"
        f"Message:\n{message}"
    )

async def remove_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.chat_id) != YOUR_ID:
        await update.message.reply_text("❌ Only Madam can remove messages!")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ Please specify which message to remove.\n\n"
            "Usage: /removemessage <name>\n"
            "Example: /removemessage special"
        )
        return
    
    name = args[0].lower()
    if name in FIXED_MESSAGES:
        await update.message.reply_text("❌ Cannot remove fixed messages.")
        return
    
    if name in CUSTOM_MESSAGES:
        del CUSTOM_MESSAGES[name]
        await update.message.reply_text(f"✅ Custom message '{name}' removed successfully!")
    else:
        await update.message.reply_text(f"❌ No custom message found with name '{name}'")

async def view_all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.chat_id) != YOUR_ID:
        await update.message.reply_text("❌ Only Madam can view messages!")
        return
    
    message_list = "📝 All Messages:\n\n"
    
    # Show fixed messages
    message_list += "🔄 Fixed Messages:\n"
    for name, message in FIXED_MESSAGES.items():
        message_list += f"\n{name.title()}:\n{message}\n"
    
    # Show custom messages
    if CUSTOM_MESSAGES:
        message_list += "\n📝 Custom Messages:\n"
        for name, message in CUSTOM_MESSAGES.items():
            message_list += f"\n{name.title()}:\n{message}\n"
    else:
        message_list += "\n📝 No custom messages added yet.\n"
    
    message_list += "\nCommands:\n"
    message_list += "• /addmessage <name> <message> - Add new message\n"
    message_list += "• /removemessage <name> - Remove custom message\n"
    message_list += "• /sendmessage - Send a message to all employees"
    
    await update.message.reply_text(message_list)

async def send_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.chat_id) != YOUR_ID:
        await update.message.reply_text("❌ Only Madam can send messages!")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ Please specify which message to send.\n\n"
            "Usage: /sendmessage <name>\n"
            "Example: /sendmessage morning"
        )
        return
    
    name = args[0].lower()
    message = FIXED_MESSAGES.get(name) or CUSTOM_MESSAGES.get(name)
    
    if not message:
        await update.message.reply_text(f"❌ No message found with name '{name}'")
        return
    
    # Send message to all employees
    success_count = 0
    for employee_name, chat_id in EMPLOYEES.items():
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=message
            )
            success_count += 1
            logger.info(f"Sent message '{name}' to {employee_name}")
        except Exception as e:
            logger.error(f"Failed to send message '{name}' to {employee_name}: {e}")
    
    await update.message.reply_text(
        f"✅ Message '{name}' sent to {success_count} employees successfully!"
    )

# Webhook handlers
@app.route('/')
async def health_check():
    global LAST_PING
    time_since_last_ping = datetime.now() - LAST_PING
    status = "healthy" if time_since_last_ping < timedelta(minutes=15) else "warning"
    return {
        "status": status,
        "last_ping": LAST_PING.isoformat(),
        "time_since_last_ping": str(time_since_last_ping),
        "bot_running": True
    }, 200

@app.route(f'/webhook/{BOT_TOKEN}', methods=['POST'])
async def webhook():
    logger.info("Webhook hit")
    data = await request.get_json(force=True)
    update = Update.de_json(data, application.bot)
    if not update:
        logger.info("Update parsing failed")
        return "Update parsing failed", 200
    await application.process_update(update)
    logger.info("Update processed")
    return "Webhook OK", 200

# Register handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("help", help_command))
application.add_handler(CommandHandler("assign", assign_task))
application.add_handler(CommandHandler("list", list_tasks))
application.add_handler(CommandHandler("concern", concern))
application.add_handler(CommandHandler("done", done_command))
application.add_handler(CommandHandler("clarify", clarify_command))
application.add_handler(CommandHandler("mydone", mydone_command))
application.add_handler(CommandHandler("addmessage", add_message))
application.add_handler(CommandHandler("removemessage", remove_message))
application.add_handler(CommandHandler("viewmessages", view_all_messages))
application.add_handler(CommandHandler("sendmessage", send_message))
application.add_handler(CallbackQueryHandler(button_callback))
application.add_handler(MessageHandler((filters.PHOTO | filters.VOICE) & filters.User(user_id=int(YOUR_ID)), handle_boss_media))
application.add_handler(MessageHandler(filters.TEXT | filters.Document.ALL | filters.VOICE & ~filters.User(user_id=int(YOUR_ID)) & filters.REPLY, handle_employee_response))
application.add_handler(MessageHandler((filters.VOICE | filters.Document.ALL | filters.PHOTO) & ~filters.User(user_id=int(YOUR_ID)), handle_concern_response))
application.add_handler(MessageHandler(filters.TEXT & ~filters.User(user_id=int(YOUR_ID)), handle_mydone_response))

# Application setup
async def setup_daily_reminders(application: Application):
    # Schedule reminders at 10 AM, 2 PM, 6 PM, and 9 PM
    reminder_times = [
        (10, 0),  # 10:00 AM
        (14, 0),  # 2:00 PM
        (18, 0),  # 6:00 PM
        (21, 0)   # 9:00 PM
    ]
    
    for hour, minute in reminder_times:
        job = application.job_queue.run_daily(
            send_daily_reminder,
            time=time(hour=hour, minute=minute),
            name=f"daily_reminder_{hour}"
        )
        logger.info(f"Scheduled daily reminder for {hour:02d}:{minute:02d}")

async def send_daily_reminder(context: ContextTypes.DEFAULT_TYPE):
    current_time = datetime.now().time()
    
    # Determine which message to send based on time
    if current_time.hour == 10:  # 10 AM
        message = FIXED_MESSAGES['morning']
    elif current_time.hour == 14:  # 2 PM
        message = FIXED_MESSAGES['afternoon']
    elif current_time.hour == 18:  # 6 PM
        message = FIXED_MESSAGES['evening']
    elif current_time.hour == 21:  # 9 PM
        message = FIXED_MESSAGES['night']
    else:
        return
    
    # Send message to all employees
    for employee_name, chat_id in EMPLOYEES.items():
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=message
            )
            logger.info(f"Sent daily reminder to {employee_name}")
        except Exception as e:
            logger.error(f"Failed to send daily reminder to {employee_name}: {e}")

async def ping():
    """Keep the bot alive by sending periodic pings"""
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(PING_URL) as response:
                    if response.status == 200:
                        global LAST_PING
                        LAST_PING = datetime.now()
                        logger.info(f"Ping successful at {LAST_PING}")
                    else:
                        logger.warning(f"Ping failed with status {response.status}")
        except Exception as e:
            logger.error(f"Ping error: {e}")
        
        # Ping every 14 minutes to stay within the 15-minute timeout
        await asyncio.sleep(14 * 60)

async def main():
    try:
        # Start self-ping in background
        ping_task = asyncio.create_task(ping())
        
        # Set up daily reminders
        await setup_daily_reminders(application)
        
        # Start the bot
        await application.initialize()
        await application.start()
        
        # Start the web server
        port = int(os.getenv('PORT', 8000))
        config = uvicorn.Config(app, host='0.0.0.0', port=port)
        server = uvicorn.Server(config)
        
        # Run both the bot and web server
        await asyncio.gather(
            application.run_polling(allowed_updates=Update.ALL_TYPES),
            server.serve()
        )
    except Exception as e:
        logger.error(f"Error in main: {e}")
        raise
    finally:
        # Clean up
        if 'ping_task' in locals():
            ping_task.cancel()
            try:
                await ping_task
            except asyncio.CancelledError:
                pass
        await application.stop()
        await application.shutdown()

if __name__ == '__main__':
    try:
        # Create and set event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Run the main function
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot stopped due to error: {e}")
    finally:
        loop.close()