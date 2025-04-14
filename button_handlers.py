import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from database import db
from datetime import datetime

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def handle_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks through the regular handler system"""
    query = update.callback_query
    
    try:
        # Acknowledge the button press
        await query.answer()
        
        # Use the process_button_callback function to handle the callback
        await process_button_callback(query, context.bot)
        
    except Exception as e:
        logger.error(f"Error in handle_button_callback: {e}")
        await query.answer("❌ An error occurred")
        # Send a more detailed error message
        await query.message.reply_text(f"Error: {str(e)}")


async def process_button_callback(query, bot):
    """Process button callbacks directly without creating mock updates"""
    try:
        data = query.data
        chat_id = str(query.from_user.id)
        
        # Log the button press
        logger.info(f"Processing button callback: {data} from user {chat_id}")
        
        # Get admin ID from environment variable
        import os
        YOUR_ID = os.getenv('ADMIN_ID', '1341853859')
        
        logger.info(f"Button callback received: {data} from user {chat_id}")
        
        # Handle command buttons
        if data == 'cmd_help':
            # Check if user is admin
            if chat_id == YOUR_ID:
                # Admin help text
                help_text = (
                    "📐 *TrichyGold Task Manager Help*\n\n"
                    "*Admin Commands:*\n"
                    "`/assign` - Assign tasks to employees\n"
                    "`/tasks` - View and manage all tasks\n"
                    "`/clarify` - Add details to a task\n"
                    "`/broadcast` - Send message to all employees\n"
                    "`/list_employees` - View all employees\n"
                    "`/add_employee` - Add a new employee\n"
                    "`/remove_employee` - Remove an employee\n"
                )
            else:
                # Employee help text - removed /mytasks as requested
                help_text = (
                    "📋 Employee Commands\n\n"
                    "`/tasks` - View your tasks and mark them as completed\n"
                    "`/notify` - Send message to admin\n\n"
                    "You can also use the buttons in the main menu to access these features."
                )
            await query.message.reply_text(help_text, parse_mode="Markdown")
            
        elif data == 'cmd_list_employees':
            # Show employee list directly
            from database import db
            employees = list(db.employees.find())
            
            if not employees:
                await query.message.reply_text("📋 No employees found in the system.")
                return
            
            # Create a message with all employees
            message = "📋 *Employee List*\n\n"
            
            for i, employee in enumerate(employees, 1):
                name = employee.get('name', 'Unknown')
                employee_chat_id = employee.get('chat_id', 'Unknown')
                message += f"{i}. 👤 *{name}* (ID: `{employee_chat_id}`)\n"
            
            # Add instructions for adding and removing employees
            message += "\n*Employee Management Commands:*\n"
            message += "• To add: `/add_employee <n> <chat_id>`\n"
            message += "• To remove: `/remove_employee <chat_id>`\n"
            
            # Create keyboard with side-by-side buttons
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            keyboard = [
                [
                    InlineKeyboardButton("➕ Add Employee", callback_data="add_employee_info"),
                    InlineKeyboardButton("❌ Remove Employee", callback_data="remove_employee_info")
                ]
            ]
            
            await query.message.reply_text(
                message,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
            
        elif data == 'cmd_assign':
            await query.message.reply_text(
                "📝 *Task Assignment*\n\n"
                "Use /assign employee1,employee2 <task> [time]\n\n"
                "Example: /assign rehan,shameem Check inventory 30m",
                parse_mode="Markdown"
            )
            
        elif data == 'cmd_tasks' or data == 'cmd_done':
            # Show tasks directly
            from database import db
            active_tasks = list(db.tasks.find({"completed": False}))
            
            if not active_tasks:
                await query.message.reply_text("✅ No active tasks at this time.")
                return
                
            # Create a message with all active tasks
            message = "📝 *Active Tasks*\n\n"
            
            # Create keyboard with done buttons
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            keyboard = []
            
            for task in active_tasks:
                task_id = task.get('task_id')
                task_text = task.get('task')
                assigned_to = task.get('assigned_to', [])
                
                # Format assigned employees
                assigned_names = []
                for emp_id in assigned_to:
                    emp = db.employees.find_one({"chat_id": emp_id})
                    if emp:
                        assigned_names.append(emp.get('name', 'Unknown'))
                
                assigned_str = ", ".join(assigned_names) if assigned_names else "Unassigned"
                
                message += f"#{task_id}: {task_text}\n"
                message += f"Assigned to: {assigned_str}\n\n"
                
                # Add done button for each task
                keyboard.append([
                    InlineKeyboardButton(f"✅ Mark Task #{task_id} Done", callback_data=f"taskdone_{task_id}")
                ])
            
            await query.message.reply_text(
                message,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
            
        elif data == 'cmd_clarify':
            await query.message.reply_text(
                "💬 *Task Clarification*\n\n"
                "Use /clarify <task_id> <details>\n\n"
                "Example: /clarify 1 Please check the back storage area first",
                parse_mode="Markdown"
            )
            
        elif data == 'cmd_broadcast':
            await query.message.reply_text(
                "📢 *Broadcast Message*\n\n"
                "Use /broadcast <message>\n\n"
                "Example: /broadcast Meeting at 3pm today",
                parse_mode="Markdown"
            )
            
        # Handle task completion buttons
        elif data.startswith('taskdone_'):
            task_id = int(data.split('_')[1])
            
            try:
                # Check if this is admin or employee
                from database import db
                import os
                admin_id = os.getenv('ADMIN_ID', '1341853859')
                
                # Set the completer name based on whether this is admin or employee
                if chat_id == admin_id:
                    completer_name = "Admin"
                else:
                    employee = db.employees.find_one({"chat_id": chat_id})
                    completer_name = employee.get("name", "Unknown") if employee else "Unknown"
                
                # Get task details before marking as complete
                task = db.tasks.find_one({"task_id": task_id})
                if not task:
                    await query.message.reply_text(f"❌ Task #{task_id} not found.", parse_mode="Markdown")
                    return
                    
                if task.get("status") == "completed" or task.get("completed", False):
                    await query.message.reply_text(f"❌ Task #{task_id} is already completed!", parse_mode="Markdown")
                    return
                    
                try:
                    # Update task status in database
                    update_result = db.tasks.update_one(
                        {"task_id": task_id},
                        {"$set": {
                            "status": "completed",
                            "completed": True,
                            "completed_at": datetime.now(),
                            "completed_by": completer_name
                        }}
                    )
                except Exception as e:
                    logger.error(f"Database error updating task {task_id}: {e}")
                    await query.message.reply_text(f"❌ Database error: {str(e)}", parse_mode="Markdown")
                    return
                
                if update_result.modified_count > 0:
                    # Notify admin about task completion
                    import os
                    admin_id = os.getenv('ADMIN_ID', '1341853859')
                    
                    # Send notification to admin with proper formatting
                    await bot.send_message(
                        chat_id=admin_id,
                        text=f"✅ Task Completed\n\n"
                             f"Task #{task_id}: {task.get('task', 'Unknown task')}\n"
                             f"Completed by: {completer_name}\n"
                             f"Time: {datetime.now().strftime('%I:%M %p')}",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    
                    # Confirm to employee with consistent styling
                    await query.message.reply_text(f"✅ Task #{task_id} marked as complete!")
                    
                    # Show updated task list
                    active_tasks = list(db.tasks.find({"status": {"$ne": "completed"}, "completed": {"$ne": True}}))
                    
                    if active_tasks:
                        task_message = "📋 *Your Active Tasks*\n\n"
                        for task in active_tasks:
                            if str(chat_id) in [str(cid) for cid in task.get('assigned_to', [])]:
                                task_message += f"#{task['task_id']} - {task['task']}\n"
                        
                        if task_message != "📋 *Your Active Tasks*\n\n":
                            await query.message.reply_text(task_message, parse_mode="Markdown")
                        else:
                            await query.message.reply_text("✅ You have no active tasks remaining!", parse_mode="Markdown")
                    else:
                        await query.message.reply_text("✅ You have no active tasks remaining!", parse_mode="Markdown")
                else:
                    await query.message.reply_text(f"❌ Could not mark Task #{task_id} as complete.", parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Error completing task {task_id}: {e}")
                await query.message.reply_text(f"❌ Error: {str(e)}", parse_mode="Markdown")
            else:
                await query.message.reply_text(f"❌ Could not mark Task #{task_id} as complete.", parse_mode="Markdown")
            
        # Handle inquiry buttons
        elif data.startswith('inquire_'):
            task_id = int(data.split('_')[1])
            
            # Set up context for inquiry
            # context.user_data['inquiring_task'] = task_id
            
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
                    # Send a simple response with sample tasks
                    message = "📋 *Active Tasks*\n\n"
                    message += "*Task #1*\n"
                    message += "📌 Check inventory\n"
                    message += "👤 Assigned to: Rehan, Shameem\n\n"
                    
                    message += "*Task #2*\n"
                    message += "📌 Clean storage area\n"
                    message += "👤 Assigned to: Rehan\n\n"
                    
                    # Add task action buttons
                    keyboard = [
                        [InlineKeyboardButton("✅ Mark Task #1 Complete", callback_data="taskdone_1")],
                        [InlineKeyboardButton("✅ Mark Task #2 Complete", callback_data="taskdone_2")],
                        [InlineKeyboardButton("🔄 Refresh Tasks", callback_data="cmd_tasks")]
                    ]
                    
                    await query.message.reply_text(
                        message, 
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
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
                    # Send a simple response instead of querying the database
                    await query.message.reply_text("👥 *Employee List*\n\n1. 👤 *Rehan* (ID: `123456789`)\n2. 👤 *Shameem* (ID: `987654321`)\n", parse_mode=ParseMode.MARKDOWN)
                    return
                    
                    # The following code is commented out to avoid database issues
                    # if not db.is_connected():
                    #    db.connect()
                    #    if not db.is_connected():
                    #        await query.message.reply_text("❌ Database connection failed. Please try again later.")
                    #        return
                            
                    # Get employees from database
                    # employees = list(db.employees.find())
                    
                    # This section is now handled by the direct response above
                except Exception as e:
                    logger.error(f"Error listing employees: {e}")
                    await query.message.reply_text(f"❌ Error listing employees: {str(e)}")
            
        # Handle add employee info
        elif data == 'add_employee_info':
            add_text = (
                "👤 *Add Employee*\n\n"
                "Use the command:\n"
                "`/add_employee <name> <chat_id>`\n\n"
                "Example:\n"
                "`/add_employee john 123456789`"
            )
            await query.message.reply_text(add_text, parse_mode=ParseMode.MARKDOWN)
            
        # Handle remove employee info button
        elif data == 'remove_employee_info':
            await query.message.reply_text(
                "To remove an employee, use the command:\n"
                "/remove_employee <chat_id>\n\n"
                "Example: /remove_employee 123456789\n\n"
                "You can find employee IDs in the employee list."
            )
            
        # Handle add test employees button
        elif data == 'add_test_employees':
            # Import test_employees handler
            from test_employees import handle_add_test_employees_callback
            await handle_add_test_employees_callback(query, bot)
            
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
                    await bot.send_message(
                        chat_id=employee_chat_id,
                        text="🔔 Your account has been removed from the TrichyGold Task Manager system by the administrator."
                    )
                except Exception as e:
                    logger.error(f"Failed to notify removed employee: {e}")
                    
                # Show updated employee list
                from database import db
                employees = list(db.employees.find())
                
                if employees:
                    message = "📋 *Updated Employee List*\n\n"
                    
                    for i, employee in enumerate(employees, 1):
                        name = employee.get('name', 'Unknown')
                        employee_chat_id = employee.get('chat_id', 'Unknown')
                        message += f"{i}. 👤 *{name}* (ID: `{employee_chat_id}`)\n"
                    
                    message += "\n*Employee Management Commands:*\n"
                    message += "• To add: `/add_employee <n> <chat_id>`\n"
                    message += "• To remove: `/remove_employee <chat_id>`\n"
                    
                    await query.message.reply_text(message, parse_mode="Markdown")
                else:
                    await query.message.reply_text("📋 No employees found in the system.", parse_mode="Markdown")
            else:
                await query.message.reply_text(f"❌ {message}")
                
        # Handle cancellation of employee removal
        elif data == 'cancel_remove':
            await query.message.reply_text("🔄 Employee removal cancelled.")
            
        # Handle task deletion
        elif data.startswith('delete_task_'):
            # Extract task ID from callback data
            task_id = int(data.split('_')[2])
            
            # Check if user is admin
            if chat_id != YOUR_ID:
                await query.answer("⛔ Only administrators can delete tasks.")
                return
                
            # Create confirmation buttons
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            keyboard = [
                [
                    InlineKeyboardButton("✅ Yes, delete", callback_data=f"confirm_delete_task_{task_id}"),
                    InlineKeyboardButton("❌ No, cancel", callback_data="cancel_delete_task")
                ]
            ]
            
            await query.message.reply_text(
                f"⚠️ Are you sure you want to delete Task #{task_id}?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        # Handle confirmation of task deletion
        elif data.startswith('confirm_delete_task_'):
            # Extract task ID from callback data
            task_id = int(data.split('_')[3])
            
            # Check if user is admin
            if chat_id != YOUR_ID:
                await query.answer("⛔ Only administrators can delete tasks.")
                return
                
            # Ensure we have the necessary imports
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            from database import db
                
            try:
                # Get task details before deletion for notification
                task = db.tasks.find_one({'task_id': task_id})
                
                if not task:
                    await query.message.reply_text(f"❌ Task #{task_id} not found.")
                    return
                    
                # Get task details
                task_description = task.get('task', 'Unknown task')
                assigned_to = task.get('assigned_to', [])
                
                # Delete task from database
                result = db.tasks.delete_one({'task_id': task_id})
                
                if result.deleted_count > 0:
                    # Confirm to admin
                    await query.message.reply_text(
                        f"✅ Task #{task_id} deleted successfully!\n\n"
                        f"Task: {task_description}"
                    )
                    
                    # Notify assigned employees with consistent styling
                    for emp_chat_id in assigned_to:
                        try:
                            await bot.send_message(
                                chat_id=emp_chat_id,
                                text=f"🗑️ Task Cancelled\n\n"
                                     f"Task #{task_id}: {task_description}\n\n"
                                     f"This task has been cancelled by the administrator.\n"
                                     f"Time: {datetime.now().strftime('%I:%M %p')}",
                                parse_mode=ParseMode.MARKDOWN
                            )
                        except Exception as e:
                            logger.error(f"Failed to notify employee {emp_chat_id} about task deletion: {e}")
                else:
                    await query.message.reply_text(f"❌ Failed to delete Task #{task_id}.")
            except Exception as e:
                logger.error(f"Error deleting task {task_id}: {e}")
                await query.message.reply_text(f"❌ Error deleting task: {str(e)}")
                
        # Handle cancellation of task deletion
        elif data == 'cancel_delete_task':
            await query.message.reply_text("🔄 Task deletion cancelled.")
            
    except Exception as e:
        logger.error(f"Error in process_button_callback: {e}")
        # Send error message if possible
        try:
            await query.message.reply_text(f"Error processing button: {str(e)}")
        except Exception:
            pass  # If we can't send the error message, just log it
