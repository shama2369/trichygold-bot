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
CONCERN_CONTEXT = {}

@app.route('/')
async def health_check():
    return "Bot is running", 200  # UptimeRobot pings this

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
        await update.message.reply_text("Only Madam can assign!")
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
            confirmation = await update.message.reply_text(f"Sent to {employee}: {task}.")
            if context.job_queue is None:
                logger.error("Job queue is None!")
                await update.message.reply_text("Error: Reminder scheduling failed.")
                return
            job = context.job_queue.run_repeating(send_reminder, interval=minutes * 60, first=minutes * 60, data={'chat_id': chat_id, 'task': task})
            logger.info(f"Scheduled repeating reminder for task '{task}' every {minutes} minutes")
            CONTEXT[confirmation.message_id] = {
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

async def concern(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    if chat_id not in EMPLOYEES.values():
        await update.message.reply_text("Only employees can raise concerns!")
        return
    args = context.args
    employee_name = [name for name, eid in EMPLOYEES.items() if eid == chat_id][0]
    
    if args:
        concern_message = ' '.join(args)
        await context.bot.send_message(chat_id=YOUR_ID, text=f"{employee_name} raised concern: {concern_message}")
        await update.message.reply_text("Concern sent to Madam.")
    else:
        msg = await update.message.reply_text("Send your concern as voice or file.")
        CONCERN_CONTEXT[chat_id] = {'prompt_msg_id': msg.message_id, 'employee': employee_name}

async def handle_concern_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    if chat_id not in EMPLOYEES.values() or chat_id not in CONCERN_CONTEXT:
        return
    
    if not update.message.reply_to_message:
        return
    
    concern_info = CONCERN_CONTEXT.get(chat_id)
    reply_msg_id = update.message.reply_to_message.message_id
    if reply_msg_id != concern_info['prompt_msg_id']:
        return
    
    employee_name = concern_info['employee']
    if update.message.voice:
        voice_id = update.message.voice.file_id
        await context.bot.send_voice(chat_id=YOUR_ID, voice=voice_id, caption=f"{employee_name} raised concern")
        await update.message.reply_text("Voice concern sent to Madam.")
    elif update.message.document or update.message.photo:
        file_id = update.message.document.file_id if update.message.document else update.message.photo[-1].file_id
        await context.bot.send_document(chat_id=YOUR_ID, document=file_id, caption=f"{employee_name} raised concern")
        await update.message.reply_text("File concern sent to Madam.")
    else:
        await update.message.reply_text("Please send a voice or file.")
        return
    
    del CONCERN_CONTEXT[chat_id]

async def done_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    if chat_id != YOUR_ID:
        await update.message.reply_text("Only Madam can use /done!")
        return
    for boss_msg_id, task_info in list(CONTEXT.items()):
        if task_info['chat_id'] == chat_id:
            employee = task_info['employee']
            task = task_info['task']
            await context.bot.send_message(chat_id=YOUR_ID, text=f"{employee} completed '{task}' ✅")
            if task_info['job']:
                task_info['job'].schedule_removal()  # Stop reminders on done
            del CONTEXT[boss_msg_id]
            break
    else:
        await update.message.reply_text("No active task to mark done.")

async def handle_boss_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    if chat_id != YOUR_ID or not update.message.reply_to_message:
        return
    
    reply_msg_id = update.message.reply_to_message.message_id
    if reply_msg_id not in CONTEXT:
        return
    
    task_info = CONTEXT[reply_msg_id]
    employee_chat_id = task_info['chat_id']
    
    if update.message.photo:
        photo_file = update.message.photo[-1].file_id
        await context.bot.send_photo(chat_id=employee_chat_id, photo=photo_file, caption=f"Task clarification: {task_info['task']}")
        await context.bot.send_photo(chat_id=YOUR_ID, photo=photo_file, caption=f"Clarification sent to {task_info['employee']}: {task_info['task']}")
        await update.message.reply_text(f"Photo clarification sent to {task_info['employee']}.")
    elif update.message.voice:
        voice_file = update.message.voice.file_id
        await context.bot.send_voice(chat_id=employee_chat_id, voice=voice_file, caption=f"Task clarification: {task_info['task']}")
        await context.bot.send_voice(chat_id=YOUR_ID, voice=voice_file, caption=f"Clarification sent to {task_info['employee']}: {task_info['task']}")
        await update.message.reply_text(f"Voice clarification sent to {task_info['employee']}.")
    else:
        await update.message.reply_text("Reply with a photo or voice to clarify the task.")

async def handle_employee_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    if chat_id not in EMPLOYEES.values() or not update.message.reply_to_message:
        return
    
    reply_msg_id = update.message.reply_to_message.message_id
    logger.info(f"Reply received to message ID: {reply_msg_id}")
    
    for boss_msg_id, task_info in list(CONTEXT.items()):
        if task_info['task_msg_id'] == reply_msg_id and task_info['chat_id'] == chat_id:
            employee = task_info['employee']
            task = task_info['task']
            if update.message.text and update.message.text.lower() == 'done':
                await context.bot.send_message(chat_id=YOUR_ID, text=f"{employee} completed '{task}' ✅")
                if task_info['job']:
                    task_info['job'].schedule_removal()  # Stop reminders on done
                del CONTEXT[boss_msg_id]
            elif update.message.text:
                await context.bot.send_message(chat_id=YOUR_ID, text=f"{employee} on '{task}': {update.message.text}")
                await update.message.reply_text("Response sent to Madam.")
            elif update.message.document:
                file_id = update.message.document.file_id
                await context.bot.send_document(chat_id=YOUR_ID, document=file_id, caption=f"{employee} on '{task}'")
                await update.message.reply_text("File sent to Madam.")
            elif update.message.voice:
                voice_id = update.message.voice.file_id
                await context.bot.send_voice(chat_id=YOUR_ID, voice=voice_id, caption=f"{employee} on '{task}'")
                await update.message.reply_text("Voice sent to Madam.")
            return

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("assign", assign_task))
application.add_handler(CommandHandler("concern", concern))
application.add_handler(CommandHandler("done", done_command))
application.add_handler(MessageHandler(filters.PHOTO | filters.VOICE & filters.User(user_id=int(YOUR_ID)) & filters.REPLY, handle_boss_media))
application.add_handler(MessageHandler(filters.TEXT | filters.Document.ALL | filters.VOICE & ~filters.User(user_id=int(YOUR_ID)) & filters.REPLY, handle_employee_response))
application.add_handler(MessageHandler((filters.VOICE | filters.Document.ALL | filters.PHOTO) & ~filters.User(user_id=int(YOUR_ID)) & filters.REPLY, handle_concern_response))

async def run_application():
    await application.initialize()
    await application.start()
    await asyncio.Event().wait()

async def setup_webhook():
    url = f"https://trichygold-bot.onrender.com/webhook/{BOT_TOKEN}"
    response = await application.bot.set_webhook(url=url)
    logger.info(f"Webhook set: {response}")

async def main():
    asyncio.create_task(run_application())
    await setup_webhook()
    config = uvicorn.Config(app=app, host="0.0.0.0", port=8080, loop="asyncio")
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == '__main__':
    asyncio.run(main())