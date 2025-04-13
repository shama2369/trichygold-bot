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
            
            # Execute the appropriate command directly with immediate responses
            if data == 'cmd_assign':
                await query.message.reply_text(
                    "📝 *Task Assignment*\n\n"
                    "Use /assign employee1,employee2 <task> [time]\n\n"
                    "Example: /assign rehan,shameem Check inventory 30m",
                    parse_mode=ParseMode.MARKDOWN
                )
            elif data == 'cmd_done' or data == 'cmd_tasks':
                # Show active tasks directly
                await query.message.reply_text("📋 *Active Tasks*\n\nFetching your tasks...", parse_mode=ParseMode.MARKDOWN)
                
                # For tasks, we'll implement a direct response instead of calling the command
                try:
                    if not db.is_connected():
                        db.connect()
                        if not db.is_connected():
                            await query.message.reply_text("❌ Database connection failed. Please try again later.")
                            return
                            
                    # Get tasks from database
                    tasks = list(db.tasks.find({"completed": False}))
                    
                    if not tasks:
                        await query.message.reply_text("📋 No active tasks found.")
                        return
                        
                    # Format tasks
                    message = "📋 *Active Tasks*\n\n"
                    for task in tasks:
                        task_id = task.get('task_id')
                        task_text = task.get('task')
                        assigned_to = task.get('assigned_to', [])
                        assigned_names = [db.get_employee_name(emp_id) for emp_id in assigned_to]
                        assigned_str = ", ".join(assigned_names) if assigned_names else "Unknown"
                        
                        message += f"*Task #{task_id}*\n"
                        message += f"📌 {task_text}\n"
                        message += f"👤 Assigned to: {assigned_str}\n\n"
                    
                    await query.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
                except Exception as e:
                    logger.error(f"Error fetching tasks: {e}")
                    await query.message.reply_text(f"❌ Error fetching tasks: {str(e)}")
            elif data == 'cmd_help':
                # Direct help message
                help_text = (
                    "🔑 *TrichyGold Bot Commands*\n\n"
                    "/start - Start the bot\n"
                    "/help - Show this help message\n"
                    "/assign - Assign tasks to employees\n"
                    "/tasks - View and manage tasks\n"
                    "/clarify - Add details to tasks\n"
                    "/broadcast - Send message to all employees\n"
                    "/list_employees - List all registered employees\n"
                )
                await query.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
            elif data == 'cmd_clarify':
                await query.message.reply_text(
                    "💬 *Task Clarification*\n\n"
                    "Use /clarify <task_id> <details>\n\n"
                    "Example: /clarify 1 Please check the back storage area first",
                    parse_mode=ParseMode.MARKDOWN
                )
            elif data == 'cmd_broadcast':
                await query.message.reply_text(
                    "📢 *Broadcast Message*\n\n"
                    "Use /broadcast <message>\n\n"
                    "Example: /broadcast Meeting at 3pm today",
                    parse_mode=ParseMode.MARKDOWN
                )
            elif data == 'cmd_list_employees':
                await query.answer("Fetching employee list...")
                
                # Direct employee listing
                try:
                    if not db.is_connected():
                        db.connect()
                        if not db.is_connected():
                            await query.message.reply_text("❌ Database connection failed. Please try again later.")
                            return
                            
                    # Get employees from database
                    employees = list(db.employees.find())
                    
                    if not employees:
                        # No employees found, offer to add test employees
                        keyboard = [
                            [InlineKeyboardButton("➕ Add Test Employees", callback_data="add_test_employees")],
                            [InlineKeyboardButton("➕ Add Employee Manually", callback_data="add_employee")]
                        ]
                        await query.message.reply_text(
                            "📋 No employees found in the system.\n\nWould you like to add test employees?",
                            reply_markup=InlineKeyboardMarkup(keyboard)
                        )
                        return
                    
                    # Format employee list
                    message = "👥 *Registered Employees*\n\n"
                    
                    for i, employee in enumerate(employees, 1):
                        name = employee.get('name', 'Unknown')
                        employee_chat_id = employee.get('chat_id', 'Unknown')
                        message += f"{i}. 👤 *{name}* (ID: `{employee_chat_id}`)\n"
                    
                    # Add buttons to manage employees
                    keyboard = [
                        [InlineKeyboardButton("➕ Add Employee", callback_data="add_employee")],
                        [InlineKeyboardButton("🔄 Refresh List", callback_data="cmd_list_employees")]
                    ]
                    
                    # Add remove buttons for each employee
                    for employee in employees:
                        name = employee.get('name', 'Unknown')
                        employee_chat_id = employee.get('chat_id', 'Unknown')
                        keyboard.append([
                            InlineKeyboardButton(f"❌ Remove {name}", callback_data=f"remove_employee_{employee_chat_id}")
                        ])
                    
                    await query.message.reply_text(
                        message,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode=ParseMode.MARKDOWN
                    )
                except Exception as e:
                    logger.error(f"Error listing employees: {e}")
                    await query.message.reply_text(f"❌ Error listing employees: {str(e)}")
            
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
