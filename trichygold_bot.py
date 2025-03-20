import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from flask import Flask
import threading
import os

BOT_TOKEN = '7358468280:AAHWN3RO_911mvpX-NLyF9Y8nXCycrIs6oA'
YOUR_ID = '1341853859'  # From /start
EMPLOYEES = {
   
    'shameem': '1341853859',  # Add this with real ID
    # Your other 5 employees
}

app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot is running", 200

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat_id
    await update.message.reply_text(f"Hi! Your chat ID is {chat_id}. Boss uses /assign or sends voice (then text with name) or attachments with a caption (e.g., 'john').")

async def assign_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if str(update.message.chat_id) != YOUR_ID:
        await update.message.reply_text("Sorry, only the boss can assign tasks!")
        return
    try:
        text = ' '.join(context.args)
        employee, task = text.split(' ', 1)
        employee = employee.lower()
        if employee in EMPLOYEES:
            employee_id = EMPLOYEES[employee]
            await context.bot.send_message(chat_id=employee_id, text=f"New task from the boss: {task}")
            await update.message.reply_text(f"Task SENT to {employee}: {task}")
        else:
            await update.message.reply_text(f"Employee '{employee}' not found. Available: {list(EMPLOYEES.keys())}")
    except Exception as e:
        await update.message.reply_text(f"Usage: /assign <employee> <task>. Example: /assign john Polish the rings")

async def handle_voice_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if str(update.message.chat_id) != YOUR_ID:
        await update.message.reply_text("Sorry, only the boss can assign tasks!")
        return
    try:
        caption = update.message.caption
        employee = caption.lower() if caption else None
        print(f"Voice task - Raw caption: '{caption}', Processed: '{employee}'")
        if not employee:
            await update.message.reply_text("No caption detected. Please send the employee name (e.g., 'john') as the next message.")
            context.user_data['pending_voice'] = update.message.voice.file_id
            return
        if employee not in EMPLOYEES:
            await update.message.reply_text(f"Employee '{employee}' not found. Available: {list(EMPLOYEES.keys())}")
            return
        employee_id = EMPLOYEES[employee]
        voice_file = await update.message.voice.get_file()
        await context.bot.send_voice(chat_id=employee_id, voice=voice_file.file_id, caption="New voice task from the boss")
        await update.message.reply_text(f"Voice task SENT to {employee}")
    except Exception as e:
        await update.message.reply_text(f"Error sending voice task: {str(e)}")

async def handle_attachment_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if str(update.message.chat_id) != YOUR_ID:
        await update.message.reply_text("Sorry, only the boss can assign tasks!")
        return
    try:
        caption = update.message.caption
        employee = caption.lower() if caption else None
        print(f"Attachment task - Raw caption: '{caption}', Processed: '{employee}'")
        if not employee:
            await update.message.reply_text("Please include the employee name as a caption (e.g., 'john') with your attachment.")
            return
        if employee not in EMPLOYEES:
            await update.message.reply_text(f"Employee '{employee}' not found. Available: {list(EMPLOYEES.keys())}")
            return
        employee_id = EMPLOYEES[employee]
        if update.message.photo:
            photo_file = await update.message.photo[-1].get_file()
            await context.bot.send_photo(chat_id=employee_id, photo=photo_file.file_id, caption="New task attachment from the boss")
        elif update.message.document:
            doc_file = await update.message.document.get_file()
            await context.bot.send_document(chat_id=employee_id, document=doc_file.file_id, caption="New task attachment from the boss")
        else:
            await update.message.reply_text("Unsupported attachment type. Send a photo or document.")
            return
        await update.message.reply_text(f"Attachment task SENT to {employee}")
    except Exception as e:
        await update.message.reply_text(f"Error sending attachment task: {str(e)}")

async def handle_employee_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    employee_id = str(update.message.chat_id)
    for name, emp_id in EMPLOYEES.items():
        if employee_id == emp_id:
            if update.message.voice:
                voice_file = await update.message.voice.get_file()
                await context.bot.send_voice(chat_id=YOUR_ID, voice=voice_file.file_id, caption=f"{name} sent a voice reply")
                await update.message.reply_text("Your voice reply sent to the boss!")
            elif update.message.photo:
                photo_file = await update.message.photo[-1].get_file()
                await context.bot.send_photo(chat_id=YOUR_ID, photo=photo_file.file_id, caption=f"{name} sent a reply attachment")
                await update.message.reply_text("Your attachment sent to the boss!")
            elif update.message.document:
                doc_file = await update.message.document.get_file()
                await context.bot.send_document(chat_id=YOUR_ID, document=doc_file.file_id, caption=f"{name} sent a reply attachment")
                await update.message.reply_text("Your attachment sent to the boss!")
            return
    await update.message.reply_text("Sorry, I only handle replies from employees.")

async def handle_text_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if str(update.message.chat_id) != YOUR_ID or 'pending_voice' not in context.user_data:
        return
    employee = update.message.text.lower()
    if employee in EMPLOYEES:
        employee_id = EMPLOYEES[employee]
        voice_file_id = context.user_data.pop('pending_voice')
        await context.bot.send_voice(chat_id=employee_id, voice=voice_file_id, caption="New voice task from the boss")
        await update.message.reply_text(f"Voice task SENT to {employee}")
    else:
        await update.message.reply_text(f"Employee '{employee}' not found. Available: {list(EMPLOYEES.keys())}")

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Sorry, I didn’t understand that. Use /start, /assign (boss only), or send a voice/attachment.")

def run_bot():
    lock_file = '/tmp/bot.lock'
    if os.path.exists(lock_file):
        print("Another instance is running. Exiting...")
        return
    with open(lock_file, 'w') as f:
        f.write(str(os.getpid()))
    try:
        application = Application.builder().token(BOT_TOKEN).build()
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("assign", assign_task))
        application.add_handler(MessageHandler(filters.VOICE & ~filters.COMMAND, handle_voice_task))
        application.add_handler(MessageHandler((filters.PHOTO | filters.Document.ALL) & ~filters.COMMAND, handle_attachment_task))
        application.add_handler(MessageHandler((filters.VOICE | filters.PHOTO | filters.Document.ALL) & ~filters.COMMAND, handle_employee_reply))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_reply))
        application.add_handler(MessageHandler(filters.COMMAND, unknown))
        print("Bot is running...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    finally:
        if os.path.exists(lock_file):
            os.remove(lock_file)

if __name__ == '__main__':
    flask_thread = threading.Thread(target=lambda: app.run(host='0.0.0.0', port=8080))
    flask_thread.daemon = True
    flask_thread.start()
    run_bot()



