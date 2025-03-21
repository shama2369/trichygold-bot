from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from flask import Flask, request

BOT_TOKEN = '7358468280:AAGktrhJSHmhHWlW8KmME_ST5P6VQkoj_Vo'
YOUR_ID = '1341853859'  # From /start
EMPLOYEES = {
   
    'shameem': '1341853859',  # Add this with real ID
    # Your other 5 employees
}

app = Flask(__name__)
application = Application.builder().token(BOT_TOKEN).build()

@app.route('/')
def health_check():
    return "Bot is running", 200

@app.route(f'/webhook/{BOT_TOKEN}', methods=['POST'])
async def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    await application.process_update(update)
    return '', 200

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Hi! Your chat ID is {update.message.chat_id}.")

async def assign_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.chat_id) != YOUR_ID:
        await update.message.reply_text("Only the boss can assign tasks!")
        return
    try:
        text = ' '.join(context.args)
        employee, task = text.split(' ', 1)
        employee = employee.lower()
        if employee in EMPLOYEES:
            await context.bot.send_message(chat_id=EMPLOYEES[employee], text=f"New task: {task}")
            await update.message.reply_text(f"Task SENT to {employee}: {task}")
        else:
            await update.message.reply_text(f"Employee '{employee}' not found.")
    except ValueError:
        await update.message.reply_text("Use: /assign <employee> <task>")

async def handle_voice_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.chat_id) != YOUR_ID:
        return
    caption = update.message.caption
    employee = caption.lower() if caption else None
    if not employee:
        await update.message.reply_text("Send employee name (e.g., 'john').")
        context.user_data['pending_voice'] = update.message.voice.file_id
        return
    if employee in EMPLOYEES:
        voice_file = await update.message.voice.get_file()
        await context.bot.send_voice(chat_id=EMPLOYEES[employee], voice=voice_file.file_id)
        await update.message.reply_text(f"Voice task SENT to {employee}")

async def handle_attachment_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.chat_id) != YOUR_ID:
        return
    caption = update.message.caption
    employee = caption.lower() if caption else None
    if not employee:
        await update.message.reply_text("Send employee name as caption.")
        return
    if employee in EMPLOYEES:
        if update.message.photo:
            photo_file = await update.message.photo[-1].get_file()
            await context.bot.send_photo(chat_id=EMPLOYEES[employee], photo=photo_file.file_id)
        elif update.message.document:
            doc_file = await update.message.document.get_file()
            await context.bot.send_document(chat_id=EMPLOYEES[employee], document=doc_file.file_id)
        await update.message.reply_text(f"Attachment task SENT to {employee}")

async def handle_employee_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    employee_id = str(update.message.chat_id)
    employee = next((emp for emp, eid in EMPLOYEES.items() if eid == employee_id), None)
    if employee and (update.message.voice or update.message.photo or update.message.document):
        if update.message.voice:
            voice_file = await update.message.voice.get_file()
            await context.bot.send_voice(chat_id=YOUR_ID, voice=voice_file.file_id, caption=f"Reply from {employee}")
        elif update.message.photo:
            photo_file = await update.message.photo[-1].get_file()
            await context.bot.send_photo(chat_id=YOUR_ID, photo=photo_file.file_id, caption=f"Reply from {employee}")
        elif update.message.document:
            doc_file = await update.message.document.get_file()
            await context.bot.send_document(chat_id=YOUR_ID, document=doc_file.file_id, caption=f"Reply from {employee}")
        await update.message.reply_text("Reply sent to boss!")

async def handle_text_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.chat_id) != YOUR_ID or 'pending_voice' not in context.user_data:
        return
    employee = update.message.text.lower()
    if employee in EMPLOYEES:
        voice_file_id = context.user_data.pop('pending_voice')
        await context.bot.send_voice(chat_id=EMPLOYEES[employee], voice=voice_file_id)
        await update.message.reply_text(f"Voice task SENT to {employee}")

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Unknown command. Try /start or /assign.")

# Register handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("assign", assign_task))
application.add_handler(MessageHandler(filters.VOICE & ~filters.COMMAND, handle_voice_task))
application.add_handler(MessageHandler((filters.PHOTO | filters.Document.ALL) & ~filters.COMMAND, handle_attachment_task))
application.add_handler(MessageHandler((filters.VOICE | filters.PHOTO | filters.Document.ALL) & ~filters.COMMAND, handle_employee_reply))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_reply))
application.add_handler(MessageHandler(filters.COMMAND, unknown))

if __name__ == '__main__':
    print("Bot is setting up...")
    render_url = "https://trichygold-bot.onrender.com"  # Update after deploy
    webhook_url = f"{render_url}/webhook/{BOT_TOKEN}"
    application.bot.set_webhook(url=webhook_url)
    app.run(host='0.0.0.0', port=8080)


















