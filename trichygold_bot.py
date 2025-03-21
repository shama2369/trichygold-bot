import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from quart import Quart, request
import traceback
import uvicorn

BOT_TOKEN = '7358468280:AAGktrhJSHmhHWlW8KmME_ST5P6VQkoj_Vo'
YOUR_ID = '1341853859'
EMPLOYEES = {
    'shameem': '1341853859',
}

app = Quart(__name__)
application = Application.builder().token(BOT_TOKEN).build()

@app.route('/')
async def health_check():
    print("Health check called!")
    return "Bot is running", 200

@app.route(f'/webhook/{BOT_TOKEN}', methods=['POST'])
async def webhook():
    print("Webhook route hit!")
    try:
        data = await request.get_json(force=True)
        print(f"Received data: {data}")
        update = Update.de_json(data, application.bot)
        if not update:
            print("Failed to parse update: Update is None")
            return "Update parsing failed", 200
        print(f"Update parsed: {update.update_id}")
        await application.process_update(update)
        print("Update processed successfully")
        return "Webhook OK", 200
    except Exception as e:
        print(f"Webhook error: {str(e)}")
        traceback.print_exc()
        return f"Error: {str(e)}", 500

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Processing /start from {update.message.chat_id}")
    await update.message.reply_text(f"Hi! Your chat ID is {update.message.chat_id}. Use /assign <employee> <task>.")

async def assign_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Processing /assign from {update.message.chat_id}")
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

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("assign", assign_task))

async def setup_webhook():
    render_url = "https://trichygold-bot.onrender.com"
    webhook_url = f"{render_url}/webhook/{BOT_TOKEN}"
    try:
        await application.initialize()
        response = await application.bot.set_webhook(url=webhook_url)
        print(f"Webhook set response: {response}")
        if response:
            print(f"Webhook successfully set to {webhook_url}")
        else:
            print("Webhook setup failed!")
    except Exception as e:
        print(f"Webhook setup error: {e}")
        traceback.print_exc()

async def main():
    print("Bot is setting up...")
    await setup_webhook()
    config = uvicorn.Config(app=app, host="0.0.0.0", port=8080, loop="asyncio")
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == '__main__':
    asyncio.run(main())