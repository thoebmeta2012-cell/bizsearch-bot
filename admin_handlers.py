"""
Admin handlers for MOC Bot
Provides admin controls for broadcast, user management, logs, and statistics
"""

import asyncio
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


def get_admin_menu_keyboard():
    """Create admin menu keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("📊 Statistics", callback_data="admin_stats"),
            InlineKeyboardButton("👥 Users", callback_data="admin_users")
        ],
        [
            InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast"),
            InlineKeyboardButton("📜 Logs", callback_data="admin_logs")
        ],
        [
            InlineKeyboardButton("🔍 Search History", callback_data="admin_search_history"),
            InlineKeyboardButton("💾 Database Info", callback_data="admin_db_info")
        ],
        [
            InlineKeyboardButton("🔙 Back to Main Menu", callback_data="menu_main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_back_to_admin_keyboard():
    """Create back to admin menu keyboard."""
    keyboard = [[InlineKeyboardButton("🔙 Back to Admin Menu", callback_data="admin_menu")]]
    return InlineKeyboardMarkup(keyboard)


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /admin command - show admin menu."""
    user_id = update.effective_user.id
    db = context.bot_data.get('database')
    
    if not db:
        await update.message.reply_text("❌ Database not initialized")
        return
    
    # Check if user is admin
    if not db.is_admin(user_id):
        await update.message.reply_text("❌ You don't have admin privileges")
        db.log_interaction(user_id, 'admin_denied', command='/admin', success=False)
        return
    
    db.log_interaction(user_id, 'admin_access', command='/admin')
    
    await update.message.reply_text(
        "🔐 *Admin Panel*\n\n"
        "Welcome to the admin control panel.\n"
        "Choose an option below:",
        parse_mode='Markdown',
        reply_markup=get_admin_menu_keyboard()
    )


async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show bot statistics."""
    query = update.callback_query
    await query.answer()
    
    db = context.bot_data.get('database')
    user_id = query.from_user.id
    
    if not db or not db.is_admin(user_id):
        await query.edit_message_text("❌ Access denied")
        return
    
    # Get statistics
    user_stats = db.get_user_stats()
    search_stats = db.get_search_stats()
    db_info = db.get_database_size()
    
    message = "📊 *Bot Statistics*\n\n"
    
    # User stats
    message += "*👥 Users:*\n"
    message += f"• Total Users: {user_stats.get('total_users', 0)}\n"
    message += f"• Active Today: {user_stats.get('active_today', 0)}\n"
    message += f"• Active This Week: {user_stats.get('active_week', 0)}\n"
    message += f"• Admins: {user_stats.get('total_admins', 0)}\n"
    message += f"• Blocked: {user_stats.get('blocked_users', 0)}\n\n"
    
    # Search stats
    message += "*🔍 Searches:*\n"
    message += f"• Total Searches: {search_stats.get('total_searches', 0)}\n"
    message += f"• Today: {search_stats.get('searches_today', 0)}\n"
    message += f"• This Week: {search_stats.get('searches_week', 0)}\n"
    message += f"• Unique Users: {search_stats.get('unique_users', 0)}\n"
    message += f"• Avg Results: {search_stats.get('avg_results_per_search', 0):.1f}\n"
    message += f"• Avg Duration: {search_stats.get('avg_duration', 0):.1f}s\n\n"
    
    # Database stats
    message += "*💾 Database:*\n"
    message += f"• Size: {db_info.get('size_mb', 0)} MB\n"
    message += f"• Users: {db_info.get('users_count', 0)}\n"
    message += f"• Searches: {db_info.get('search_history_count', 0)}\n"
    message += f"• Results: {db_info.get('search_results_count', 0)}\n"
    message += f"• Interactions: {db_info.get('interactions_count', 0)}\n"
    message += f"• Exports: {db_info.get('exports_count', 0)}\n"
    
    await query.edit_message_text(
        message,
        parse_mode='Markdown',
        reply_markup=get_back_to_admin_keyboard()
    )


async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user management options."""
    query = update.callback_query
    await query.answer()
    
    db = context.bot_data.get('database')
    user_id = query.from_user.id
    
    if not db or not db.is_admin(user_id):
        await query.edit_message_text("❌ Access denied")
        return
    
    # Get recent users
    users = db.get_all_users(limit=10)
    
    message = "👥 *User Management*\n\n"
    message += f"*Recent Users (Last 10):*\n\n"
    
    for i, user in enumerate(users, 1):
        username = user['username'] or 'N/A'
        first_name = user['first_name'] or 'Unknown'
        admin_badge = " 👑" if user['is_admin'] else ""
        blocked_badge = " 🚫" if user['is_blocked'] else ""
        
        message += f"{i}. {first_name} (@{username}){admin_badge}{blocked_badge}\n"
        message += f"   ID: `{user['user_id']}`\n"
        message += f"   Searches: {user['total_searches']} | Exports: {user['total_exports']}\n"
        message += f"   Last Active: {user['last_active'][:16]}\n\n"
    
    message += "\n*Commands:*\n"
    message += "`/setadmin <user_id>` - Make user admin\n"
    message += "`/removeadmin <user_id>` - Remove admin\n"
    message += "`/block <user_id>` - Block user\n"
    message += "`/unblock <user_id>` - Unblock user\n"
    message += "`/userinfo <user_id>` - Get user details\n"
    
    await query.edit_message_text(
        message,
        parse_mode='Markdown',
        reply_markup=get_back_to_admin_keyboard()
    )


async def admin_broadcast_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show broadcast menu."""
    query = update.callback_query
    await query.answer()
    
    db = context.bot_data.get('database')
    user_id = query.from_user.id
    
    if not db or not db.is_admin(user_id):
        await query.edit_message_text("❌ Access denied")
        return
    
    # Get recent broadcasts
    broadcasts = db.get_broadcasts(limit=5)
    
    message = "📢 *Broadcast Management*\n\n"
    
    if broadcasts:
        message += "*Recent Broadcasts:*\n\n"
        for i, bc in enumerate(broadcasts, 1):
            status_emoji = "✅" if bc['status'] == 'completed' else "⏳"
            message += f"{i}. {status_emoji} {bc['message_text'][:30]}...\n"
            message += f"   Sent: {bc['successful_sends']}/{bc['total_users']}\n"
            message += f"   Date: {bc['created_at'][:16]}\n\n"
    
    message += "\n*Send Broadcast:*\n"
    message += "Use `/broadcast <message>` to send to all users\n"
    message += "Use `/broadcast_active <message>` for active users only\n\n"
    message += "*Example:*\n"
    message += "`/broadcast Hello everyone! New features available.`"
    
    await query.edit_message_text(
        message,
        parse_mode='Markdown',
        reply_markup=get_back_to_admin_keyboard()
    )


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE, target_type: str = 'all'):
    """Handle broadcast command."""
    user_id = update.effective_user.id
    db = context.bot_data.get('database')
    
    if not db or not db.is_admin(user_id):
        await update.message.reply_text("❌ You don't have admin privileges")
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ Please provide a message to broadcast\n\n"
            "*Usage:* `/broadcast Your message here`",
            parse_mode='Markdown'
        )
        return
    
    message_text = ' '.join(context.args)
    
    # Create broadcast record
    broadcast_id = db.create_broadcast(user_id, message_text, target_type)
    
    # Get target users
    target_users = db.get_broadcast_targets(target_type)
    
    status_msg = await update.message.reply_text(
        f"📢 Starting broadcast to {len(target_users)} users...\n"
        f"Target: {target_type}\n\n"
        "This may take a few moments..."
    )
    
    # Send broadcast
    successful = 0
    failed = 0
    
    for target_user_id in target_users:
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=f"📢 *Broadcast Message*\n\n{message_text}",
                parse_mode='Markdown'
            )
            successful += 1
            
            # Small delay to avoid rate limiting
            if successful % 20 == 0:
                await asyncio.sleep(1)
                await status_msg.edit_text(
                    f"📢 Broadcasting...\n"
                    f"Sent: {successful}/{len(target_users)}\n"
                    f"Failed: {failed}"
                )
        except Exception as e:
            failed += 1
            logger.warning(f"Failed to send broadcast to {target_user_id}: {e}")
    
    # Update broadcast status
    db.update_broadcast_status(broadcast_id, successful, failed, 'completed')
    db.log_admin_action(user_id, 'broadcast', details=f"Sent to {successful}/{len(target_users)} users")
    
    await status_msg.edit_text(
        f"✅ *Broadcast Complete*\n\n"
        f"Target: {target_type}\n"
        f"Total Users: {len(target_users)}\n"
        f"Successful: {successful}\n"
        f"Failed: {failed}",
        parse_mode='Markdown'
    )


async def admin_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin logs."""
    query = update.callback_query
    await query.answer()
    
    db = context.bot_data.get('database')
    user_id = query.from_user.id
    
    if not db or not db.is_admin(user_id):
        await query.edit_message_text("❌ Access denied")
        return
    
    logs = db.get_admin_logs(limit=20)
    
    message = "📜 *Admin Activity Logs*\n\n"
    
    if logs:
        for i, log in enumerate(logs[:10], 1):
            admin_name = log['admin_username'] or 'Unknown'
            message += f"{i}. *{log['action']}*\n"
            message += f"   By: @{admin_name}\n"
            if log['target_user_id']:
                message += f"   Target: {log['target_user_id']}\n"
            if log['details']:
                message += f"   Details: {log['details'][:50]}\n"
            message += f"   Time: {log['created_at'][:16]}\n\n"
    else:
        message += "No admin logs found."
    
    await query.edit_message_text(
        message,
        parse_mode='Markdown',
        reply_markup=get_back_to_admin_keyboard()
    )


async def admin_search_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show popular searches and search statistics."""
    query = update.callback_query
    await query.answer()
    
    db = context.bot_data.get('database')
    user_id = query.from_user.id
    
    if not db or not db.is_admin(user_id):
        await query.edit_message_text("❌ Access denied")
        return
    
    popular = db.get_popular_searches(limit=10)
    
    message = "🔍 *Search Analytics*\n\n"
    message += "*Most Popular Searches:*\n\n"
    
    for i, search in enumerate(popular, 1):
        message += f"{i}. `{search['search_term']}`\n"
        message += f"   Searches: {search['search_count']}\n\n"
    
    await query.edit_message_text(
        message,
        parse_mode='Markdown',
        reply_markup=get_back_to_admin_keyboard()
    )


async def admin_db_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show database information."""
    query = update.callback_query
    await query.answer()
    
    db = context.bot_data.get('database')
    user_id = query.from_user.id
    
    if not db or not db.is_admin(user_id):
        await query.edit_message_text("❌ Access denied")
        return
    
    db_info = db.get_database_size()
    
    message = "💾 *Database Information*\n\n"
    message += f"*Size:* {db_info.get('size_mb', 0)} MB / 2048 MB\n"
    message += f"*Usage:* {(db_info.get('size_mb', 0) / 2048 * 100):.1f}%\n\n"
    
    message += "*Table Records:*\n"
    message += f"• Users: {db_info.get('users_count', 0):,}\n"
    message += f"• Search History: {db_info.get('search_history_count', 0):,}\n"
    message += f"• Search Results: {db_info.get('search_results_count', 0):,}\n"
    message += f"• Interactions: {db_info.get('interactions_count', 0):,}\n"
    message += f"• Exports: {db_info.get('exports_count', 0):,}\n"
    message += f"• Broadcasts: {db_info.get('broadcasts_count', 0):,}\n"
    message += f"• Admin Logs: {db_info.get('admin_logs_count', 0):,}\n"
    
    await query.edit_message_text(
        message,
        parse_mode='Markdown',
        reply_markup=get_back_to_admin_keyboard()
    )


async def setadmin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set user as admin."""
    user_id = update.effective_user.id
    db = context.bot_data.get('database')
    
    if not db or not db.is_admin(user_id):
        await update.message.reply_text("❌ You don't have admin privileges")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: `/setadmin <user_id>`", parse_mode='Markdown')
        return
    
    try:
        target_user_id = int(context.args[0])
        db.set_admin(target_user_id, True)
        db.log_admin_action(user_id, 'set_admin', target_user_id)
        
        await update.message.reply_text(f"✅ User {target_user_id} is now an admin")
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID")


async def removeadmin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove admin privileges."""
    user_id = update.effective_user.id
    db = context.bot_data.get('database')
    
    if not db or not db.is_admin(user_id):
        await update.message.reply_text("❌ You don't have admin privileges")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: `/removeadmin <user_id>`", parse_mode='Markdown')
        return
    
    try:
        target_user_id = int(context.args[0])
        db.set_admin(target_user_id, False)
        db.log_admin_action(user_id, 'remove_admin', target_user_id)
        
        await update.message.reply_text(f"✅ Admin privileges removed from user {target_user_id}")
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID")


async def block_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Block a user."""
    user_id = update.effective_user.id
    db = context.bot_data.get('database')
    
    if not db or not db.is_admin(user_id):
        await update.message.reply_text("❌ You don't have admin privileges")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: `/block <user_id>`", parse_mode='Markdown')
        return
    
    try:
        target_user_id = int(context.args[0])
        db.block_user(target_user_id, True)
        db.log_admin_action(user_id, 'block_user', target_user_id)
        
        await update.message.reply_text(f"✅ User {target_user_id} has been blocked")
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID")


async def unblock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unblock a user."""
    user_id = update.effective_user.id
    db = context.bot_data.get('database')
    
    if not db or not db.is_admin(user_id):
        await update.message.reply_text("❌ You don't have admin privileges")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: `/unblock <user_id>`", parse_mode='Markdown')
        return
    
    try:
        target_user_id = int(context.args[0])
        db.block_user(target_user_id, False)
        db.log_admin_action(user_id, 'unblock_user', target_user_id)
        
        await update.message.reply_text(f"✅ User {target_user_id} has been unblocked")
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID")


async def userinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get detailed user information."""
    user_id = update.effective_user.id
    db = context.bot_data.get('database')
    
    if not db or not db.is_admin(user_id):
        await update.message.reply_text("❌ You don't have admin privileges")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: `/userinfo <user_id>`", parse_mode='Markdown')
        return
    
    try:
        target_user_id = int(context.args[0])
        user = db.get_user(target_user_id)
        
        if not user:
            await update.message.reply_text("❌ User not found")
            return
        
        # Get user's search history
        searches = db.get_user_search_history(target_user_id, limit=5)
        
        message = f"👤 *User Information*\n\n"
        message += f"*ID:* `{user['user_id']}`\n"
        message += f"*Username:* @{user['username'] or 'N/A'}\n"
        message += f"*Name:* {user['first_name'] or 'Unknown'} {user['last_name'] or ''}\n"
        message += f"*Language:* {user['language_code'] or 'N/A'}\n"
        message += f"*Admin:* {'Yes 👑' if user['is_admin'] else 'No'}\n"
        message += f"*Blocked:* {'Yes 🚫' if user['is_blocked'] else 'No'}\n"
        message += f"*Joined:* {user['created_at'][:16]}\n"
        message += f"*Last Active:* {user['last_active'][:16]}\n\n"
        
        message += f"*Activity:*\n"
        message += f"• Total Searches: {user['total_searches']}\n"
        message += f"• Total Exports: {user['total_exports']}\n\n"
        
        if searches:
            message += f"*Recent Searches:*\n"
            for search in searches[:3]:
                message += f"• `{search['search_term']}` ({search['results_count']} results)\n"
        
        await update.message.reply_text(message, parse_mode='Markdown')
        
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID")
