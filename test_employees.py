import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import db

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def add_test_employees_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /add_test_employees command to add test employees to the database"""
    chat_id = str(update.message.chat_id)
    
    # Get admin ID from application data
    YOUR_ID = context.application.bot_data.get('ADMIN_ID', '')
    
    # Only admin can add test employees
    if chat_id != YOUR_ID:
        await update.message.reply_text("⛔ Sorry, only administrators can add test employees.")
        return
    
    # Check if MongoDB is connected
    if not db.is_connected():
        # Try to reconnect
        db.connect()
        await update.message.reply_text(
            "⚠️ Database connection was lost. Attempting to reconnect..."
        )
        if not db.is_connected():
            await update.message.reply_text(
                "❌ Failed to connect to database. Please check with /dbstatus."
            )
            return
    
    try:
        # Add test employees
        test_employees = [
            {"name": "John", "chat_id": "123456789"},
            {"name": "Alice", "chat_id": "987654321"},
            {"name": "Bob", "chat_id": "555555555"}
        ]
        
        success_count = 0
        for employee in test_employees:
            try:
                # Check if employee already exists
                existing = db.employees.find_one({"chat_id": employee["chat_id"]})
                if existing:
                    continue
                    
                # Add employee to database
                db.employees.insert_one(employee)
                success_count += 1
                logger.info(f"Added test employee: {employee['name']} with chat ID {employee['chat_id']}")
            except Exception as e:
                logger.error(f"Error adding test employee {employee['name']}: {e}")
        
        if success_count > 0:
            await update.message.reply_text(f"✅ Added {success_count} test employees successfully!")
        else:
            await update.message.reply_text("⚠️ No new test employees were added. They may already exist.")
        
        # Create a button to list employees
        keyboard = [[InlineKeyboardButton("📋 List Employees", callback_data="cmd_list_employees")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "Click below to view the employee list:",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Error in add_test_employees_command: {e}")
        await update.message.reply_text(f"❌ Error adding test employees: {str(e)}")

async def handle_add_test_employees_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the add_test_employees button callback"""
    query = update.callback_query
    chat_id = str(query.from_user.id)
    
    # Get admin ID from application data
    YOUR_ID = context.application.bot_data.get('ADMIN_ID', '')
    
    # Only admin can add test employees
    if chat_id != YOUR_ID:
        await query.answer("⛔ Sorry, only administrators can add test employees.")
        return
    
    await query.answer("Adding test employees...")
    
    try:
        # Check if MongoDB is connected
        if not db.is_connected():
            # Try to reconnect
            db.connect()
            await query.message.reply_text(
                "⚠️ Database connection was lost. Attempting to reconnect..."
            )
            if not db.is_connected():
                await query.message.reply_text(
                    "❌ Failed to connect to database. Please check with /dbstatus."
                )
                return
        
        # Add test employees
        test_employees = [
            {"name": "John", "chat_id": "123456789"},
            {"name": "Alice", "chat_id": "987654321"},
            {"name": "Bob", "chat_id": "555555555"}
        ]
        
        success_count = 0
        for employee in test_employees:
            try:
                # Check if employee already exists
                existing = db.employees.find_one({"chat_id": employee["chat_id"]})
                if existing:
                    continue
                    
                # Add employee to database
                db.employees.insert_one(employee)
                success_count += 1
                logger.info(f"Added test employee: {employee['name']} with chat ID {employee['chat_id']}")
            except Exception as e:
                logger.error(f"Error adding test employee {employee['name']}: {e}")
        
        if success_count > 0:
            await query.message.reply_text(f"✅ Added {success_count} test employees successfully!")
        else:
            await query.message.reply_text("⚠️ No new test employees were added. They may already exist.")
        
        # Show updated employee list
        employees = list(db.employees.find())
        
        # Create a message with all employees
        message = "📋 *Employee List*\n\n"
        
        # Create keyboard with remove buttons
        keyboard = []
        
        for i, employee in enumerate(employees, 1):
            name = employee.get('name', 'Unknown')
            employee_chat_id = employee.get('chat_id', 'Unknown')
            
            message += f"{i}. 👤 *{name}* (ID: `{employee_chat_id}`)\n"
            
            # Add remove button for each employee
            keyboard.append([
                InlineKeyboardButton(f"❌ Remove {name}", callback_data=f"remove_employee_{employee_chat_id}")
            ])
        
        # Add a button to add new employees
        keyboard.append([InlineKeyboardButton("➕ Add Employee", callback_data="add_employee")])
        keyboard.append([InlineKeyboardButton("🔄 Refresh List", callback_data="cmd_list_employees")])
        
        # Send the message with the inline keyboard
        await query.message.reply_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logger.error(f"Error adding test employees: {e}")
        await query.message.reply_text(f"❌ Error adding test employees: {str(e)}")
