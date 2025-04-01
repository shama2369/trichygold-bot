from datetime import datetime
import logging

logger = logging.getLogger(__name__)

async def handle_clarification(update, context):
    """Handle clarification media from admin"""
    chat_id = str(update.message.chat_id)
    task_id = context.user_data.get('clarifying_task')
    
    if not task_id:
        return
    
    task_info = context.bot_data.get('TASKS', {}).get(task_id)
    if not task_info:
        await update.message.reply_text("❌ Task not found!")
        return
    
    # Prepare the clarification message
    caption = f"📝 Clarification for Task #{task_id}:\n{task_info['task']}"
    
    # Send to all assigned employees
    for employee in task_info['employees']:
        try:
            if update.message.text:
                await context.bot.send_message(
                    chat_id=employee,
                    text=f"{caption}\n\n{update.message.text}"
                )
            elif update.message.voice:
                await context.bot.send_voice(
                    chat_id=employee,
                    voice=update.message.voice.file_id,
                    caption=caption
                )
            elif update.message.document:
                await context.bot.send_document(
                    chat_id=employee,
                    document=update.message.document.file_id,
                    caption=caption
                )
            elif update.message.photo:
                await context.bot.send_photo(
                    chat_id=employee,
                    photo=update.message.photo[-1].file_id,
                    caption=caption
                )
        except Exception as e:
            logger.error(f"Failed to send clarification to {employee}: {e}")
    
    await update.message.reply_text("✅ Clarification sent to all assigned employees!")
    del context.user_data['clarifying_task']

async def handle_inquiry(update, context):
    """Handle inquiry media from employees"""
    chat_id = str(update.message.chat_id)
    task_id = context.user_data.get('inquiring_task')
    
    if not task_id:
        return
    
    task_info = context.bot_data.get('TASKS', {}).get(task_id)
    if not task_info:
        await update.message.reply_text("❌ Task not found!")
        return
    
    employee_name = next((name for name, id in context.bot_data.get('EMPLOYEES', {}).items() if id == chat_id), None)
    if not employee_name:
        await update.message.reply_text("❌ Employee not found!")
        return
    
    # Prepare the inquiry message
    caption = f"❓ Question about Task #{task_id}\nFrom: {employee_name}\nTask: {task_info['task']}"
    
    # Send to admin
    try:
        if update.message.text:
            await context.bot.send_message(
                chat_id=context.bot_data['YOUR_ID'],
                text=f"{caption}\n\n{update.message.text}"
            )
        elif update.message.voice:
            await context.bot.send_voice(
                chat_id=context.bot_data['YOUR_ID'],
                voice=update.message.voice.file_id,
                caption=caption
            )
        elif update.message.document:
            await context.bot.send_document(
                chat_id=context.bot_data['YOUR_ID'],
                document=update.message.document.file_id,
                caption=caption
            )
        elif update.message.photo:
            await context.bot.send_photo(
                chat_id=context.bot_data['YOUR_ID'],
                photo=update.message.photo[-1].file_id,
                caption=caption
            )
    except Exception as e:
        logger.error(f"Failed to send inquiry to admin: {e}")
        await update.message.reply_text("❌ Failed to send inquiry. Please try again.")
        return
    
    await update.message.reply_text("✅ Your question has been sent to admin!")
    del context.user_data['inquiring_task']

async def handle_notification(update, context):
    """Handle notification media from employees"""
    chat_id = str(update.message.chat_id)
    
    if not context.user_data.get('notifying'):
        return
    
    employee_name = next((name for name, id in context.bot_data.get('EMPLOYEES', {}).items() if id == chat_id), None)
    if not employee_name:
        await update.message.reply_text("❌ Employee not found!")
        return
    
    # Prepare the notification message
    caption = f"📢 Notification from {employee_name}"
    
    # Send to admin
    try:
        if update.message.text:
            await context.bot.send_message(
                chat_id=context.bot_data['YOUR_ID'],
                text=f"{caption}\n\n{update.message.text}"
            )
        elif update.message.voice:
            await context.bot.send_voice(
                chat_id=context.bot_data['YOUR_ID'],
                voice=update.message.voice.file_id,
                caption=caption
            )
        elif update.message.document:
            await context.bot.send_document(
                chat_id=context.bot_data['YOUR_ID'],
                document=update.message.document.file_id,
                caption=caption
            )
        elif update.message.photo:
            await context.bot.send_photo(
                chat_id=context.bot_data['YOUR_ID'],
                photo=update.message.photo[-1].file_id,
                caption=caption
            )
    except Exception as e:
        logger.error(f"Failed to send notification to admin: {e}")
        await update.message.reply_text("❌ Failed to send notification. Please try again.")
        return
    
    await update.message.reply_text("✅ Your notification has been sent to admin!")
    del context.user_data['notifying']

async def handle_broadcast(update, context):
    """Handle broadcast media from admin"""
    chat_id = str(update.message.chat_id)
    
    if chat_id != context.bot_data['YOUR_ID'] or not context.user_data.get('broadcasting'):
        return
    
    # Create a unique ID for this broadcast
    broadcast_id = len(context.bot_data.get('CUSTOM_MESSAGES', {})) + 1
    
    # Store the broadcast message
    context.bot_data.setdefault('CUSTOM_MESSAGES', {})[broadcast_id] = {
        'id': broadcast_id,
        'timestamp': datetime.now(),
        'acknowledged_by': set(),
        'content_type': 'text' if update.message.text else 'media'
    }
    
    # Create acknowledgment button
    keyboard = [[{"text": "✅ Acknowledge", "callback_data": f"ack_{broadcast_id}"}]]
    
    # Send to all employees
    failed_sends = []
    for employee_name, employee_id in context.bot_data.get('EMPLOYEES', {}).items():
        try:
            if update.message.text:
                await context.bot.send_message(
                    chat_id=employee_id,
                    text=f"📢 Important Message from Admin:\n\n{update.message.text}",
                    reply_markup={"inline_keyboard": keyboard}
                )
            elif update.message.voice:
                await context.bot.send_voice(
                    chat_id=employee_id,
                    voice=update.message.voice.file_id,
                    caption="📢 Important Message from Admin",
                    reply_markup={"inline_keyboard": keyboard}
                )
            elif update.message.document:
                await context.bot.send_document(
                    chat_id=employee_id,
                    document=update.message.document.file_id,
                    caption="📢 Important Message from Admin",
                    reply_markup={"inline_keyboard": keyboard}
                )
            elif update.message.photo:
                await context.bot.send_photo(
                    chat_id=employee_id,
                    photo=update.message.photo[-1].file_id,
                    caption="📢 Important Message from Admin",
                    reply_markup={"inline_keyboard": keyboard}
                )
        except Exception as e:
            logger.error(f"Failed to send broadcast to {employee_name}: {e}")
            failed_sends.append(employee_name)
    
    if failed_sends:
        await update.message.reply_text(
            f"⚠️ Broadcast sent but failed for: {', '.join(failed_sends)}"
        )
    else:
        await update.message.reply_text(
            "✅ Broadcast sent to all employees!\n"
            "You will be notified as they acknowledge it."
        )
    
    del context.user_data['broadcasting']

async def handle_taskdone_callback(update, context, task_id):
    """Handle task completion button callback"""
    query = update.callback_query
    chat_id = str(query.message.chat_id)
    
    employee_name = next((name for name, id in context.bot_data.get('EMPLOYEES', {}).items() if id == chat_id), None)
    if not employee_name:
        await query.answer("❌ Employee not found!")
        return
    
    task_info = context.bot_data.get('TASKS', {}).get(task_id)
    if not task_info:
        await query.answer("❌ Task not found!")
        return
    
    if task_info['status'] != 'active':
        await query.answer("❌ This task is already completed!")
        return
    
    if employee_name not in task_info['employees']:
        await query.answer("❌ This task is not assigned to you!")
        return
    
    # Mark task as completed
    task_info['status'] = 'completed'
    task_info['completed_at'] = datetime.now()
    task_info['completed_by'] = employee_name
    
    # Notify admin
    await context.bot.send_message(
        chat_id=context.bot_data['YOUR_ID'],
        text=f"✅ Task #{task_id} completed by {employee_name}\n"
             f"Task: {task_info['task']}\n"
             f"Completed at: {task_info['completed_at'].strftime('%Y-%m-%d %H:%M')}"
    )
    
    await query.answer("✅ Task marked as completed!")
    await query.message.edit_text(
        f"{query.message.text}\n\n✅ Marked as completed by {employee_name}"
    )

async def handle_inquire_callback(update, context, task_id):
    """Handle inquiry button callback"""
    query = update.callback_query
    chat_id = str(query.message.chat_id)
    
    employee_name = next((name for name, id in context.bot_data.get('EMPLOYEES', {}).items() if id == chat_id), None)
    if not employee_name:
        await query.answer("❌ Employee not found!")
        return
    
    task_info = context.bot_data.get('TASKS', {}).get(task_id)
    if not task_info:
        await query.answer("❌ Task not found!")
        return
    
    if employee_name not in task_info['employees']:
        await query.answer("❌ This task is not assigned to you!")
        return
    
    # Store context for handling the next message
    context.user_data['inquiring_task'] = task_id
    
    await query.answer()
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"📝 Send your question about Task #{task_id}\n"
             f"You can send:\n"
             f"• Text message\n"
             f"• Voice message\n"
             f"• Files/Photos"
    )

async def handle_acknowledgment_callback(update, context, message_id):
    """Handle broadcast acknowledgment callback"""
    query = update.callback_query
    chat_id = str(query.message.chat_id)
    
    employee_name = next((name for name, id in context.bot_data.get('EMPLOYEES', {}).items() if id == chat_id), None)
    if not employee_name:
        await query.answer("❌ Employee not found!")
        return
    
    message_info = context.bot_data.get('CUSTOM_MESSAGES', {}).get(message_id)
    if not message_info:
        await query.answer("❌ Message not found!")
        return
    
    if employee_name in message_info['acknowledged_by']:
        await query.answer("You have already acknowledged this message!")
        return
    
    # Record acknowledgment
    message_info['acknowledged_by'].add(employee_name)
    
    # Notify admin
    await context.bot.send_message(
        chat_id=context.bot_data['YOUR_ID'],
        text=f"✅ {employee_name} acknowledged broadcast #{message_id}"
    )
    
    await query.answer("✅ Thank you for acknowledging!")
    await query.message.edit_reply_markup(reply_markup=None)  # Remove the button
