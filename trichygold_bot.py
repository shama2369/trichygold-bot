import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from quart import Quart, request
import uvicorn
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = '7358468280:AAGktrhJSHmhHWlW8KmME_ST5P6VQkoj_Vo'
YOUR_ID = '1341853859'
EMPLOYEES = {
    'shameem': '1341853859',
    'employee2': 'CHAT_ID_2',
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

app = Quart(__name__)
application = Application.builder().token(BOT_TOKEN).build()

CONTEXT = {}

@app.route('/')
async def health_check():
    return "Bot is running", 200

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Chat ID: {update.message.chat_id}. Boss: /assign <employee> <task> [minutes] + photo/voice. Employees: reply with text/file/voice, 'done' to complete.")

async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.data['chat_id']
    task = job.data['task']
    await context.bot.send_message(chat_id=chat_id, text=f"Reminder: {task}")

async def assign_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.chat_id) != YOUR_ID:
        await update.message.reply_text("Only boss can assign!")
        return
    try:
        args = context.args
        if len(args) < 2:
            raise ValueError
        employee = args[0].lower()
        # Check if last arg is minutes, otherwise it's part of task
        if len(args) > 2 and args[-1].isdigit():
            task = ' '.join(args[1:-1])
            minutes = int(args[-1])
        else:
            task = ' '.join(args[1:])
            minutes = 60  # Default
        
        if employee in EMPLOYEES:
            chat_id = EMPLOYEES[employee]
            msg = await context.bot.send_message(chat_id=chat_id, text=f"Task: {task} (Reply with text/file/voice, 'done' to complete)")
            await update.message.reply_text(f"Sent to {employee}: {task}. Reminder in {minutes} min. Reply with photo/voice if needed.")
            job = context.job_queue.run_once(send_reminder, minutes * 60, data={'chat_id': chat_id, 'task': task})
            CONTEXT[update.message.message_id] = {
                'employee': employee,
                'task': task,
                'chat_id': chat_id,
                'task_msg_id': msg.message_id,
                'job': job
            }
        else:
            await update.message.reply_text(f"'{employee}' not found. Valid employees: {', '.join(EMPLOYEES.keys())}")
    except ValueError:
        await update.message.reply_text("Use: /assign <employee> <task> [minutes]")

async def handle_boss_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.chat_id) != YOUR_ID:
        return
    if not update.message.reply_to_message or update.message.reply_to_message.message_id not in CONTEXT:
        await update.message.reply_text("Reply to your /assign message with photo/voice.")
        return
    
    boss_msg_id = update.message.reply_to_message.message_id
    task_info = CONTEXT[boss_msg_id]
    employee_chat_id = task_info['chat_id']
    
    if update.message.phot