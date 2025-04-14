"""
Employee management handlers for TrichyGold Bot
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import db
from validators import validate_employee_data, is_valid_chat_id

# Set up logging
logger = logging.getLogger(__name__)

async def add_employee_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /add_employee command to add a new employee to the system"""
    chat_id = str(update.message.chat_id)
    admin_id = context.bot_data.get('ADMIN_ID', None)
    
    # Only admin can add employees
    if chat_id != admin_id:
        await update.message.reply_text("⛔ Sorry, only administrators can add employees.")
        return
    
    # Check if we have the required arguments
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "⚠️ Please provide employee name and chat ID.\n\n"
            "Format: /add_employee <name> <chat_id>\n"
            "Example: /add_employee john 123456789"
        )
        return
    
    # Extract name and chat_id from arguments
    name = context.args[0]
    employee_chat_id = context.args[1]
    
    # Validate employee data
    is_valid, error_message = validate_employee_data(name, employee_chat_id)
    if not is_valid:
        await update.message.reply_text(f"⚠️ {error_message}")
        return
    
    try:
        # Check if MongoDB is connected
        if not db.is_connected():
            await update.message.reply_text(
                "⚠️ Database connection error. Please try again later or check with /dbstatus."
            )
            return
        
        # Check if employee already exists
        existing_employee = db.employees.find_one({'chat_id': employee_chat_id})
        if existing_employee:
            await update.message.reply_text(
                f"⚠️ Employee with chat ID {employee_chat_id} already exists as '{existing_employee['name']}'."
            )
            return
        
        # Add employee to database
        employee_data = {
            'name': name,
            'chat_id': employee_chat_id
        }
        
        db.employees.update_one(
            {'chat_id': employee_chat_id},
            {'$set': employee_data},
            upsert=True
        )
        
        logger.info(f"Added new employee: {name} with chat ID {employee_chat_id}")
        
        # Confirm to admin
        await update.message.reply_text(
            f"✅ Employee added successfully!\n\n"
            f"👤 Name: {name}\n"
            f"📱 Chat ID: {employee_chat_id}"
        )
        
        # Try to notify the employee if possible
        try:
            await context.bot.send_message(
                chat_id=employee_chat_id,
                text=f"👋 Welcome to TrichyGold Task Manager! You have been added as an employee by the administrator."
            )
        except Exception as e:
            logger.error(f"Failed to notify new employee: {e}")
            await update.message.reply_text(
                "⚠️ Employee added, but could not send welcome message. The chat ID might be incorrect or the user hasn't started the bot yet."
            )
            
    except Exception as e:
        logger.error(f"Error adding employee: {e}")
        await update.message.reply_text(
            f"❌ Error adding employee: {str(e)}\n\n"
            f"Please try again or check database connection with /dbstatus."
        )

async def remove_employee_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /remove_employee command to remove an employee from the system"""
    chat_id = str(update.message.chat_id)
    admin_id = context.bot_data.get('ADMIN_ID', None)
    
    # Only admin can remove employees
    if chat_id != admin_id:
        await update.message.reply_text("⛔ Sorry, only administrators can remove employees.")
        return
    
    # Check if we have the required arguments
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "⚠️ Please provide employee chat ID.\n\n"
            "Format: /remove_employee <chat_id>\n"
            "Example: /remove_employee 123456789"
        )
        return
    
    # Extract chat_id from arguments
    employee_chat_id = context.args[0]
    
    # Validate chat ID
    if not is_valid_chat_id(employee_chat_id):
        await update.message.reply_text("⚠️ Invalid chat ID format.")
        return
    
    try:
        # Check if MongoDB is connected
        if not db.is_connected():
            await update.message.reply_text(
                "⚠️ Database connection error. Please try again later or check with /dbstatus."
            )
            return
        
        # Check if employee exists
        existing_employee = db.employees.find_one({'chat_id': employee_chat_id})
        if not existing_employee:
            await update.message.reply_text(
                f"⚠️ No employee found with chat ID {employee_chat_id}."
            )
            return
        
        # Remove employee from database
        result = db.employees.delete_one({'chat_id': employee_chat_id})
        
        if result.deleted_count > 0:
            logger.info(f"Removed employee: {existing_employee['name']} with chat ID {employee_chat_id}")
            
            # Confirm to admin
            await update.message.reply_text(
                f"✅ Employee removed successfully!\n\n"
                f"👤 Name: {existing_employee['name']}\n"
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
        else:
            await update.message.reply_text(
                f"❌ Failed to remove employee with chat ID {employee_chat_id}."
            )
            
    except Exception as e:
        logger.error(f"Error removing employee: {e}")
        await update.message.reply_text(
            f"❌ Error removing employee: {str(e)}\n\n"
            f"Please try again or check database connection with /dbstatus."
        )

async def list_employees_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /list_employees command to show all employees"""
    chat_id = str(update.message.chat_id)
    admin_id = context.bot_data.get('ADMIN_ID', None) or context.application.bot_data.get('ADMIN_ID', None)
    
    # Only admin can list employees
    if chat_id != admin_id:
        await update.message.reply_text("⛔ Sorry, only administrators can view the employee list.")
        return
    
    try:
        # Check if MongoDB is connected
        if not db.is_connected():
            await update.message.reply_text(
                "⚠️ Database connection error. Please try again later or check with /dbstatus."
            )
            return
        
        # Get all employees from database
        employees = list(db.employees.find())
        
        if not employees:
            await update.message.reply_text("📋 No employees found in the system.")
            return
        
        # Create a message with all employees
        message = "📋 *Employee List*\n\n"
        
        for i, employee in enumerate(employees, 1):
            name = employee.get('name', 'Unknown')
            employee_chat_id = employee.get('chat_id', 'Unknown')
            
            message += f"{i}. 👤 *{name}* (ID: `{employee_chat_id}`)\n"
        
        # Add instructions for adding and removing employees
        message += "\n*Employee Management Commands:*\n"
        message += "• To add: `/add_employee <name> <chat_id>`\n"
        message += "• To remove: `/remove_employee <chat_id>`\n"
        
        # Create keyboard with side-by-side buttons
        keyboard = [
            [
                InlineKeyboardButton("➕ Add Employee", callback_data="add_employee_info"),
                InlineKeyboardButton("❌ Remove Employee", callback_data="remove_employee_info")
            ]
        ]
        
        # Send the message with the inline keyboard
        await update.message.reply_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        
        logger.info(f"Listed {len(employees)} employees for admin")
        
    except Exception as e:
        logger.error(f"Error listing employees: {e}")
        await update.message.reply_text(
            f"❌ Error listing employees: {str(e)}\n\n"
            f"Please try again or check database connection with /dbstatus."
        )
