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
    await update.message.reply_text(f"Chat ID: {update.message.chat_id}")

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
        if len(args) > 2 and args[-1].isdigit():
            task = ' '.join(args[1:-1])
            minutes = int(args[-1])
        else:
            task = ' '.join(args[1:])
            minutes = 60
        
        if employee in EMPLOYEES:
            chat_id = EMPLOYEES[employee]
            msg = await context.bot.send_message(chat_id=chat_id, text=f"Task: {task}")
            await update.message.reply_text(f"Sent to {employee}: {task}. Reminder in {minutes} min.")
            job = None
            if context.job_queue is not None:
                job = context.job_queue.run_once(send_reminder, minutes * 60, data={'chat_id': chat_id, 'task': task})
                logger.info(f"Scheduled reminder for task '{task}' in {minutes} minutes, task_msg_id: {msg.message_id}")
            else:
                logger.error("Job queue is None! Skipping reminder.")
                await update.message.reply_text("Error: Reminder scheduling failed.")
            CONTEXT[update.message.message_id] = {
                'employee': employee,
                'task': task,
                'chat_id': chat_id,
                'task_msg_id': msg.message_id,
                'job': job
            }
            logger.info(f"CONTEXT updated with boss_msg_id: {update.message.message_id}")
        else:
            await update.message.reply_text(f"'{employee}' not found. Valid employees: {', '.join(EMPLOYEES.keys())}")
    except ValueError:
        await update.message.reply_text("Use: /assign <employee> <task> [minutes]")

async def done_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    if chat_id != YOUR_ID:
        await update.message.reply_text("Only boss can use /done!")
        return
    for boss_msg_id, task_info in list(CONTEXT.items()):
        if task_info['chat_id'] == chat_id:
            employee = task_info['employee']
            task = task_info['task']
            await context.bot.send_message(chat_id=YOUR_ID, text=f"{employee} completed '{task}'")
            await update.message.reply_text(f"Task '{task}' marked complete. Reminder cancelled.")
            if task_info['job']:
                task_info['job'].schedule_removal()
            del CONTEXT[boss_msg_id]
            break
    else:
        await update.message.reply_text("No active task to mark done.")

async def handle_boss_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.chat_id) != YOUR_ID:
        return
    if not update.message.reply_to_message or update.message.reply_to_message.message_id not in CONTEXT:
        await update.message.reply_text("No task to attach media to.")
        return
    
    boss_msg_id = update.message.reply_to_message.message_id
    task_info = CONTEXT[boss_msg_id]
    employee_chat_id = task_info['chat_id']
    
    if update.message.photo:
        photo_file = update.message.photo[-1].file_id
        await context.bot.send_photo(chat_id=employee_chat_id, photo=photo_file, caption=f"Task: {task_info['task']}")
        await update.message.reply_text(f"Photo sent to {task_info['employee']}.")
    elif update.message.voice:
        voice_file = update.message.voice.file_id
        await context.bot.send_voice(chat_id=employee_chat_id, voice=voice_file, caption=f"Task: {task_info['task']}")
        await update.message.reply_text(f"Voice sent to {task_info['employee']}.")
    else:
        await update.message.reply_text("Send a photo or voice message.")

async def handle_employee_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    if chat_id not in EMPLOYEES.values():
        return
    
    text = update.message.text.lower() if update.message.text else None
    if text == 'done' and not update.message.reply_to_message:  # Standalone "done" for testing
        for boss_msg_id, task_info in list(CONTEXT.items()):
            if task_info['chat_id'] == chat_id:
                employee = task_info['employee']
                task = task_info['task']
                await context.bot.send_message(chat_id=YOUR_ID, text=f"{employee} completed '{task}'")
                await update.message.reply_text(f"Task '{task}' marked complete. Reminder cancelled.")
                if task_info['job']:
                    task_info['job'].schedule_removal()
                del CONTEXT[boss_msg_id]
                break
        return
    
    if not update.message.reply_to_message:
        return
    
    reply_msg_id = update.message.reply_to_message.message_id
    logger.info(f"Reply received to message ID: {reply_msg_id}")
    for boss_msg_id, task_info in list(CONTEXT.items()):
        logger.info(f"Checking task_msg_id: {task_info['task_msg_id']} against reply_msg_id: {reply_msg_id}")
        if task_info['task_msg_id'] == reply_msg_id and task_info['chat_id'] == chat_id:
            employee = task_info['employee']
            task = task_info['task']
            if text == 'done':
                await context.bot.send_message(chat_id=YOUR_ID, text=f"{employee} completed '{task}'")
                await update.message.reply_text("Task marked complete. Reminder cancelled.")
                if task_info['job']:
                    task_info['job'].schedule_removal()
                del CONTEXT[boss_msg_id]
            elif update.message.text:
                await context.bot.send_message(chat_id=YOUR_ID, text=f"{employee} on '{task}': {update.message.text}")
                await update.message.reply_text("Response sent to boss.")
            elif update.message.document:
                file_id = update.message.document.file_id
                await context.bot.send_document(chat_id=YOUR_ID, document=file_id, caption=f"{employee} on '{task}'")
                await update.message.reply_text("File sent to boss.")
            elif update.message.voice:
                voice_id = update.message.voice.file_id
                await context.bot.send_voice(chat_id=YOUR_ID, voice=voice_id, caption=f"{employee} on '{task}'")
                await update.message.reply_text("Voice sent to boss.")
            break

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("assign", assign_task))
application.add_handler(CommandHandler("done", done_command))
application.add_handler(MessageHandler(filters.PHOTO | filters.VOICE & filters.User(user_id=int(YOUR_ID)), handle_boss_media))
application.add_handler(MessageHandler(filters.TEXT | filters.Document.ALL | filters.VOICE & ~filters.User(user_id=int(YOUR_ID)), handle_employee_response))

async def main():
    await application.initialize()
    await application.start()
    application.job_queue.start()  # Explicitly start job queue
    await setup_webhook()
    config = uvicorn.Config(app=app, host="0.0.0.0", port=8080, loop="asyncio")
    server = uvicorn.Server(config)
    await server.serve()

async def setup_webhook():
    url = f"https://trichygold-bot.onrender.com/webhook/{BOT_TOKEN}"
    response = await application.bot.set_webhook(url=url)
    logger.info(f"Webhook set: {response}")

if __name__ == '__main__':
    asyncio.run(main())