import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from database import db

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def handle_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks from inline keyboards"""
    try:
        query = update.callback_query
        data = query.data
        chat_id = str(update.callback_query.from_user.id)
        
        # Get admin ID from application data
        YOUR_ID = context.application.bot_data.get('ADMIN_ID', '')
        
        logger.info(f"Button callback received: {data} from user {chat_id}")
        
        # Handle task completion buttons
        if data.startswith('taskdone_'):
            task_id = int(data.split('_')[1])
            await query.answer()
            
            # Create a mock update with the task ID as an argument
            context.args = [str(task_id)]
            
            # Import here to avoid circular imports
            from trichygold_botc import taskdone_command
            
            # Call the taskdone command
            await taskdone_command(update, context)
            
        # Handle inquiry buttons
        elif data.startswith('inquire_'):
            task_id = int(data.split('_')[1])
            await query.answer()
            
            # Set up context for inquiry
            context.user_data['inquiring_task'] = task_id
            
            await query.message.reply_text(
                f"📝 Send your question about Task #{task_id}\n"
                f"You can send:\n"
                f"• Text message\n"
                f"• Voice message\n"
                f"• Files/documents\n"
                f"• Photos"
            )
            
        # Handle command buttons from welcome message
        elif data.startswith('cmd_'):
            command = data.replace('cmd_', '')
            
            # Show "tasks" instead of "done" for the View Tasks button
            if command == "done":
                command = "tasks"
                
            await query.answer(f"Running command: {command}")
            
            # Import commands here to avoid circular imports
            from trichygold_botc import (
                tasks_command, help_command, clarify_command, 
                broadcast_command, db_status_command, db_reconnect_command,
                list_employees_command
            )
            
            # Execute the appropriate command directly
            if data == 'cmd_assign':
                await query.message.reply_text(
                    "Use /assign employee1,employee2 <task> [time]\n\n"
                    "Example: /assign rehan,shameem Check inventory 30m"
                )
            elif data == 'cmd_done' or data == 'cmd_tasks':
                # For commands that show task lists, execute them directly
                context.args = []
                await tasks_command(update, context)
            elif data == 'cmd_help':
                await help_command(update, context)
            elif data == 'cmd_clarify':
                await clarify_command(update, context)
            elif data == 'cmd_broadcast':
                await broadcast_command(update, context)
            elif data == 'cmd_dbreconnect':
                await db_reconnect_command(update, context)
            elif data == 'cmd_list_employees':
                # Call the list_employees_command directly
                await query.answer("Fetching employee list...")
                # Call the list_employees_command directly
                await list_employees_command(update, context)
            
        # Handle add employee button
        elif data == 'add_employee':
            await query.answer()
            await query.message.reply_text(
                "To add a new employee, use the format:\n"
                "/add_employee <name> <chat_id>\n\n"
                "Example: /add_employee John 123456789"
            )
            
        # Handle add test employees button
        elif data == 'add_test_employees':
            # Import test_employees handler
            from test_employees import handle_add_test_employees_callback
            await handle_add_test_employees_callback(update, context)
            
        # Handle employee removal
        elif data.startswith('remove_employee_'):
            # Extract employee chat ID from callback data
            employee_chat_id = data.split('_')[2]
            
            # Confirm removal
            keyboard = [
                [
                    InlineKeyboardButton("✅ Yes, remove", callback_data=f"confirm_remove_{employee_chat_id}"),
                    InlineKeyboardButton("❌ No, cancel", callback_data="cancel_remove")
                ]
            ]
            
            await query.message.reply_text(
                f"⚠️ Are you sure you want to remove employee with chat ID {employee_chat_id}?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        # Handle confirmation of employee removal
        elif data.startswith('confirm_remove_'):
            # Extract employee chat ID from callback data
            employee_chat_id = data.split('_')[2]
            
            # Check if user is admin
            if chat_id != YOUR_ID:
                await query.answer("⛔ Only administrators can remove employees.")
                return
                
            # Remove employee from database
            success, message, employee_data = db.remove_employee(employee_chat_id)
            
            if success:
                # Confirm to admin
                await query.message.reply_text(
                    f"✅ Employee removed successfully!\n\n"
                    f"👤 Name: {employee_data['name']}\n"
                    f"📱 Chat ID: {employee_chat_id}"
                )
                
                # Try to notify the employee if possible
                try:
                    await context.bot.send_message(
                        chat_id=employee_chat_id,
                        text="🔔 Your account has been removed from the TrichyGold Task Manager system by the administrator."
                    )
                except Exception as e:
                    logger.error(f"Failed to notify removed employee: {e}")
                    
                # Refresh the employee list
                # Import list_employees_command to avoid circular imports
                from employee_handlers import list_employees_command
                await list_employees_command(update, context)
            else:
                await query.message.reply_text(f"❌ {message}")
                
        # Handle cancellation of employee removal
        elif data == 'cancel_remove':
            await query.message.reply_text("🔄 Employee removal cancelled.")
            
    except Exception as e:
        logger.error(f"Error in handle_button_callback: {e}")
        await query.answer("❌ An error occurred")
        # Send a more detailed error message
        await query.message.reply_text(
            f"❌ An error occurred while processing your request: {str(e)}\n\n"
            f"Please try again or contact the administrator."
        )
