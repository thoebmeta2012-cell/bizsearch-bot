"""
Cambodia MOC Business Registry Telegram Bot
Enhanced with button menus, slash commands, and CSV export
"""

import asyncio
import csv
import io
import os
import sys
import logging
import httpx
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler,
    filters, 
    ContextTypes
)

# Add parent directory to path
from database import Database
from supabase_database import SupabaseDatabase
from admin_handlers import (
    admin_command, admin_stats, admin_users, admin_broadcast_menu,
    admin_logs, admin_search_history, admin_db_info, broadcast_command,
    setadmin_command, removeadmin_command, block_command, unblock_command,
    userinfo_command, get_admin_menu_keyboard
)
from health_server import start_health_server


class Director:
    def __init__(self, data: dict):
        self.name = data.get("name", "")
        self.position = data.get("position", "")
        self.nationality = data.get("nationality", "")
        self.appointment_date = data.get("appointment_date", "")
        self.is_chairman = data.get("is_chairman", False)
        self.is_former = data.get("is_former", False)
        self.ceased_date = data.get("ceased_date", "")


class SearchResult:
    CSV_FIELDS = [
        ("entity_name", "Company Name (English)"),
        ("entity_name_khmer", "Company Name (Khmer)"),
        ("registration_number", "Registration Number"),
        ("original_id", "ID"),
        ("status", "Status"),
        ("registration_date", "Incorporation Date"),
        ("re_registration_date", "Re-Registration Date"),
        ("entity_type", "Entity Type"),
        ("tin", "Tax ID Number"),
        ("tax_registration_date", "Tax Registration Date"),
        ("annual_return_date", "Annual Return Date"),
        ("address", "Address"),
    ]

    def __init__(self, data: dict):
        self.entity_name = data.get("entity_name", "")
        self.entity_name_khmer = data.get("entity_name_khmer", "")
        self.registration_number = data.get("registration_number", "")
        self.original_id = data.get("original_id", "")
        self.status = data.get("status", "")
        self.registration_date = data.get("registration_date", "")
        self.re_registration_date = data.get("re_registration_date", "")
        self.entity_type = data.get("entity_type", "")
        self.tin = data.get("tin", "")
        self.tax_registration_date = data.get("tax_registration_date", "")
        self.annual_return_date = data.get("annual_return_date", "")
        self.address = data.get("address", "")
        self.details_url = data.get("details_url", "")
        self.directors: List[Director] = [Director(d) for d in data.get("directors", [])]

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if k != "directors"} | {
            "directors": [d.__dict__ for d in self.directors]
        }

    def to_csv_row(self) -> list:
        return [getattr(self, field) for field, _ in self.CSV_FIELDS]

    @classmethod
    def csv_headers(cls) -> list:
        return [label for _, label in cls.CSV_FIELDS]

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token - set this as environment variable
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')

# MOC API configuration
API_BASE_URL = os.getenv('MOC_API_URL', 'https://bizsearch.up.railway.app')
API_KEY = os.getenv('MOC_API_KEY', 'moc_HNhgXE4sZSXO7iBeUYOyICD4yz0ASncwDsBh5yV9g0M')

# Initialize database (use /app/data in Docker, current dir otherwise)
use_supabase = os.getenv('USE_SUPABASE', 'false').lower() == 'true'
if use_supabase:
    logger.info("Using Supabase PostgreSQL database")
    db = SupabaseDatabase()
else:
    db_path = '/app/data/mocbot.db' if os.path.exists('/app/data') else 'mocbot.db'
    db = Database(db_path)
    logger.info(f"SQLite database initialized at: {db_path}")

# Initialize admin users from environment variable
admin_ids_str = os.getenv('ADMIN_IDS', '')
if admin_ids_str:
    try:
        admin_ids = [int(id.strip()) for id in admin_ids_str.split(',') if id.strip()]
        for admin_id in admin_ids:
            # Check if user exists and is already admin
            user = db.get_user(admin_id)
            if not user:
                # Create user entry if doesn't exist
                db.add_or_update_user(admin_id, username="admin", first_name="Admin")
                logger.info(f"Created admin user entry for {admin_id}")
            
            if not db.is_admin(admin_id):
                db.set_admin(admin_id, True)
                logger.info(f"✅ Set user {admin_id} as admin")
            else:
                logger.info(f"User {admin_id} is already an admin")
    except Exception as e:
        logger.error(f"Error setting up admin users: {e}")
else:
    logger.warning("No ADMIN_IDS environment variable set")

# Store user search history (in production, use a database)
user_search_history = {}

# Track active searches for cancellation
active_searches = {}

# Global search counter for monitoring
concurrent_searches = 0
MAX_CONCURRENT_SEARCHES = 8  # Limit total concurrent searches

# Thread pool for running sync scraper in async context
executor = ThreadPoolExecutor(max_workers=3)


def get_main_menu_keyboard():
    """Create main menu keyboard with buttons."""
    keyboard = [
        [
            InlineKeyboardButton("🔍 Search Company", callback_data="menu_search"),
            InlineKeyboardButton("👤 Search Director", callback_data="menu_search_director"),
        ],
        [
            InlineKeyboardButton("📊 Export CSV", callback_data="menu_export"),
            InlineKeyboardButton("📜 Search History", callback_data="menu_history"),
        ],
        [
            InlineKeyboardButton("ℹ️ Help", callback_data="menu_help"),
            InlineKeyboardButton("📖 About", callback_data="menu_about"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_export_keyboard():
    """Create export options keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("📥 Export Last Search", callback_data="export_last"),
        ],
        [
            InlineKeyboardButton("🔙 Back to Menu", callback_data="menu_main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_back_keyboard():
    """Create back button keyboard."""
    keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data="menu_main")]]
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send welcome message with main menu."""
    user = update.effective_user
    
    # Add or update user in database
    db.add_or_update_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        language_code=user.language_code,
        is_bot=user.is_bot
    )
    
    # Check if user is blocked
    if db.is_blocked(user.id):
        await update.message.reply_text("❌ You have been blocked from using this bot.")
        return
    
    db.log_interaction(user.id, 'command', command='/start')
    
    welcome_message = """
🏢 *Cambodia MOC Business Registry Bot*

Welcome! I can help you search for business entities registered with the Cambodia Ministry of Commerce.

*Quick Actions:*
• Click buttons below to navigate
• Type a company name to search directly
• Use 👤 Search Director for person search

*Available Commands:*
/search - Search for a company
/sd - Search for a director
/export - Export last search to CSV
/history - View search history
/help - Show help information
/about - About this bot

Choose an option below to get started! 👇
"""
    await update.message.reply_text(
        welcome_message,
        parse_mode='Markdown',
        reply_markup=get_main_menu_keyboard()
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help information."""
    help_text = """
📖 *Help - How to Use This Bot*

*Search Methods:*
1️⃣ Company search: Type company name or use /search
   Example: `ACLEDA` or `/search AEON`

2️⃣ Director search: Click "👤 Search Director" or use /sd
   Example: Type a person name after clicking the button

3️⃣ Using menu: Click buttons below to navigate

*Company Search Results:*
• Company name (English & Khmer)
• Registration number
• Status, Entity Type, TIN
• Incorporation/Re-registration dates
• Full address
• Click "📄 Get Full Details" to see directors

*Director Search Results:*
• Find all companies associated with a person
• View position/role in each company
• Registration numbers for each company

*Detailed Information:*
• Click "📄 Get Full Details" on any company result
• View complete directors list with:
  - Positions, Nationality, Appointment dates
  - Chairman status, Former directors

*Export to CSV:*
• Use `/export` command after a search
• Or click "📊 Export CSV" in menu

*Search History:*
• View recent searches with `/history`
• Or click "📜 Search History" in menu

*Tips:*
✓ Use partial names for broader results
✓ Search is case-insensitive
✓ Get detailed director info with one click
✓ Director search returns all companies for a person

Need more help? Use the menu buttons below! 👇
"""
    
    # Check if this is a callback query or command
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            help_text,
            parse_mode='Markdown',
            reply_markup=get_back_keyboard()
        )
    else:
        await update.message.reply_text(
            help_text,
            parse_mode='Markdown',
            reply_markup=get_main_menu_keyboard()
        )


async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show about information."""
    about_text = """
ℹ️ *About This Bot*

*Cambodia MOC Business Registry Bot*
Version 2.0 - Enhanced Edition

*Features:*
✅ Real-time business registry search
✅ Complete company information
✅ CSV export functionality
✅ Search history tracking
✅ Interactive button menus
✅ Fast results (15-20 seconds)

*Data Source:*
Ministry of Commerce, Cambodia
Official Business Registration Portal

*Technology:*
• Python + Playwright
• Telegram Bot API
• Docker-ready deployment

*Developer:*
Built with ❤️ for easy business research

*Privacy:*
Search history is stored temporarily and not shared with third parties.

Use the menu below to continue! 👇
"""
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            about_text,
            parse_mode='Markdown',
            reply_markup=get_back_keyboard()
        )
    else:
        await update.message.reply_text(
            about_text,
            parse_mode='Markdown',
            reply_markup=get_main_menu_keyboard()
        )


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle search command."""
    # Get search term from command args
    if context.args:
        search_term = ' '.join(context.args)
        await perform_search(update, context, search_term)
    else:
        await update.message.reply_text(
            "❌ Please provide a company name to search.\n\n"
            "*Usage:* `/search Company Name`\n"
            "*Example:* `/search C.NO Construction`",
            parse_mode='Markdown',
            reply_markup=get_main_menu_keyboard()
        )
    
    
async def search_director_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /sd command - search for a director."""
    if context.args:
        search_term = ' '.join(context.args)
        await perform_director_search(update, context, search_term)
    else:
        await update.message.reply_text(
            "👤 *Search Director*\n\n"
            "Please type the person/director name you want to search for.\n\n"
            "*Usage:* `/sd Person Name`\n"
            "*Example:* `/sd John Doe`",
            parse_mode='Markdown',
            reply_markup=get_main_menu_keyboard()
        )


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's search history."""
    user_id = update.effective_user.id
    history = user_search_history.get(user_id, [])
    
    if not history:
        message = "📜 *Search History*\n\nYou haven't made any searches yet.\n\nTry searching for a company to get started!"
    else:
        message = "📜 *Your Recent Searches*\n\n"
        for i, item in enumerate(history[-10:], 1):  # Show last 10
            search_term = item['search_term']
            timestamp = item['timestamp']
            results_count = item['results_count']
            message += f"{i}. `{search_term}` - {results_count} result(s)\n   _{timestamp}_\n\n"
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            message,
            parse_mode='Markdown',
            reply_markup=get_back_keyboard()
        )
    else:
        await update.message.reply_text(
            message,
            parse_mode='Markdown',
            reply_markup=get_main_menu_keyboard()
        )


async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Export last search results to CSV."""
    user_id = update.effective_user.id
    history = user_search_history.get(user_id, [])
    
    if not history:
        message = "❌ No search results to export.\n\nPlease perform a search first!"
        
        if update.callback_query:
            await update.callback_query.answer("No results to export")
            await update.callback_query.edit_message_text(
                message,
                parse_mode='Markdown',
                reply_markup=get_back_keyboard()
            )
        else:
            await update.message.reply_text(
                message,
                parse_mode='Markdown',
                reply_markup=get_main_menu_keyboard()
            )
        return
    
    # Get last search results
    last_search = history[-1]
    results = last_search.get('results', [])
    search_term = last_search['search_term']
    search_type = last_search.get('search_type', 'company')
    
    if not results:
        await update.message.reply_text(
            "❌ No results found in last search to export.",
            reply_markup=get_main_menu_keyboard()
        )
        return
    
    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    if search_type == 'director':
        # Director CSV: one row per company affiliation
        writer.writerow(["Director Name", "Company Name", "Registration Number", "Position"])
        for person in results:
            person_name = person.get('person_name', 'Unknown')
            for comp in person.get('companies', []):
                writer.writerow([
                    person_name,
                    comp.get('company_name', ''),
                    comp.get('registration_number', ''),
                    comp.get('position', ''),
                ])
        csv_file_name = f"director_search_{search_term.replace(' ', '_')}.csv"
    else:
        # Company CSV
        writer.writerow(SearchResult.csv_headers())
        for result in results:
            writer.writerow(result.to_csv_row())
        csv_file_name = f"moc_search_{search_term.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    # Convert to bytes
    csv_bytes = output.getvalue().encode('utf-8-sig')
    csv_file = io.BytesIO(csv_bytes)
    csv_file.name = csv_file_name
    
    # Send file
    caption = f"📊 *CSV Export*\n\nSearch: `{search_term}`\nResults: {len(results)}\nDate: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    
    if update.callback_query:
        await update.callback_query.answer("Generating CSV...")
        await update.callback_query.message.reply_document(
            document=csv_file,
            caption=caption,
            parse_mode='Markdown',
            reply_markup=get_main_menu_keyboard()
        )
    else:
        await update.message.reply_document(
            document=csv_file,
            caption=caption,
            parse_mode='Markdown',
            reply_markup=get_main_menu_keyboard()
        )


async def perform_search(update: Update, context: ContextTypes.DEFAULT_TYPE, search_term: str):
    """Perform the actual search operation."""
    global concurrent_searches
    
    user_id = update.effective_user.id
    username = update.effective_user.username or f"User_{user_id}"
    
    # Check if user already has an active search
    if user_id in active_searches:
        if update.callback_query:
            await update.callback_query.answer("❌ You already have an active search. Please wait or cancel it first.", show_alert=True)
        else:
            await update.message.reply_text(
                "❌ You already have an active search running.\n\n"
                "Please wait for it to complete or cancel it first.",
                reply_markup=get_main_menu_keyboard()
            )
        return
    
    # Check global concurrent search limit
    if concurrent_searches >= MAX_CONCURRENT_SEARCHES:
        message = (
            f"🚦 *System Busy*\n\n"
            f"Currently processing {concurrent_searches} searches.\n"
            f"Please try again in a few moments.\n\n"
            f"💡 *Tip*: The bot can handle up to {MAX_CONCURRENT_SEARCHES} searches simultaneously."
        )
        if update.callback_query:
            await update.callback_query.answer("System busy, please try again", show_alert=True)
            await update.callback_query.message.reply_text(message, parse_mode='Markdown', reply_markup=get_main_menu_keyboard())
        else:
            await update.message.reply_text(message, parse_mode='Markdown', reply_markup=get_main_menu_keyboard())
        return
    
    # Update user activity
    db.update_user_activity(user_id)
    
    # Check if user is blocked
    if db.is_blocked(user_id):
        if update.callback_query:
            await update.callback_query.message.reply_text("❌ You have been blocked from using this bot.")
        else:
            await update.message.reply_text("❌ You have been blocked from using this bot.")
        return
    
    # Log interaction
    db.log_interaction(user_id, 'search', message_text=search_term)
    
    # Create cancel button
    cancel_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel Search", callback_data=f"cancel_search_{user_id}")]
    ])
    
    # Send "searching" message with cancel button
    if update.callback_query:
        status_message = await update.callback_query.message.reply_text(
            f"🔍 Searching for: *{search_term}*\n\n"
            "Please wait, this should take 1-3 seconds...\n\n"
            "💡 You can cancel this search anytime using the button below.",
            parse_mode='Markdown',
            reply_markup=cancel_keyboard
        )
    else:
        status_message = await update.message.reply_text(
            f"🔍 Searching for: *{search_term}*\n\n"
            "Please wait, this should take 1-3 seconds...\n\n"
            "💡 You can cancel this search anytime using the button below.",
            parse_mode='Markdown',
            reply_markup=cancel_keyboard
        )
    
    # Mark search as active and increment counter
    concurrent_searches += 1
    active_searches[user_id] = {
        'search_term': search_term,
        'status_message': status_message,
        'cancelled': False,
        'username': username,
        'start_time': datetime.now()
    }
    
    logger.info(f"🔍 User {username} ({user_id}) started search for: {search_term} | Active searches: {concurrent_searches}/{MAX_CONCURRENT_SEARCHES}")
    
    try:
        # Perform the search in a separate thread to avoid blocking async loop
        logger.info(f"User {user_id} searching for: {search_term}")
        
        # Run sync scraper in thread pool
        loop = asyncio.get_event_loop()
        
        import time
        start_time = time.time()
        
        def run_api_search():
            if user_id in active_searches and active_searches[user_id]['cancelled']:
                return None
            try:
                with httpx.Client(timeout=60) as client:
                    resp = client.post(
                        f"{API_BASE_URL}/api/v1/search/company",
                        json={"company_name": search_term, "include_directors": False, "use_cache": True},
                        headers={"X-API-Key": API_KEY},
                    )
                data = resp.json()
                if data.get("success"):
                    return [SearchResult(r) for r in data.get("results", [])]
                return []
            except Exception as e:
                logger.error(f"API search error: {e}", exc_info=True)
                return []

        results = await asyncio.wait_for(
            loop.run_in_executor(executor, run_api_search),
            timeout=75.0
        )
        
        search_duration = time.time() - start_time
        
        # Store in database
        search_id = db.add_search(
            user_id=user_id,
            search_term=search_term,
            entity_type='Companies',
            results_count=len(results),
            max_pages=10,
            duration=search_duration
        )
        
        # Store results in database
        for result in results:
            db.add_search_result(search_id, result.to_dict())
        
        # Store in memory for quick access (keep for backward compatibility)
        if user_id not in user_search_history:
            user_search_history[user_id] = []
        
        user_search_history[user_id].append({
            'search_term': search_term,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'results_count': len(results),
            'results': results,
            'search_id': search_id
        })
        
        # Keep only last 20 searches in memory
        if len(user_search_history[user_id]) > 20:
            user_search_history[user_id] = user_search_history[user_id][-20:]
        
        if not results:
            await status_message.edit_text(
                f"❌ No results found for: *{search_term}*\n\n"
                "Try:\n"
                "• Using a different spelling\n"
                "• Using partial name\n"
                "• Checking the company name",
                parse_mode='Markdown',
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        # Create export button
        export_keyboard = [
            [InlineKeyboardButton("📥 Export to CSV", callback_data="export_last")],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="menu_main")]
        ]
        
        # Format and send results
        await status_message.edit_text(
            f"✅ Found *{len(results)}* result(s) for: *{search_term}*\n\n"
            f"Sending results...",
            parse_mode='Markdown'
        )
        
        for i, result in enumerate(results, 1):
            message = f"*📋 Result {i}/{len(results)}*\n\n"
            message += f"*Company (EN):* {result.entity_name}\n"
            
            if result.entity_name_khmer:
                message += f"*Company (KH):* {result.entity_name_khmer}\n"
            
            message += f"*Registration #:* `{result.registration_number}`\n"
            
            if result.original_id:
                message += f"*Original ID:* {result.original_id}\n"
            
            if result.status:
                message += f"*Status:* {result.status}\n"
            
            if result.registration_date:
                message += f"*Incorporation Date:* {result.registration_date}\n"
            
            if result.re_registration_date:
                message += f"*Re-Registration Date:* {result.re_registration_date}\n"
            
            if result.entity_type:
                message += f"*Type:* {result.entity_type}\n"
            
            if result.tin:
                message += f"*TIN:* {result.tin}\n"
            
            if result.tax_registration_date:
                message += f"*Tax Reg. Date:* {result.tax_registration_date}\n"
            
            if result.annual_return_date:
                message += f"*Annual Return:* {result.annual_return_date}\n"
            
            if result.directors:
                message += f"\n*👔 Directors ({len(result.directors)}):*\n"
                for j, director in enumerate(result.directors[:5], 1):  # Show max 5 directors
                    message += f"{j}. {director.name}"
                    if director.position:
                        message += f" - {director.position}"
                    if director.nationality:
                        message += f" ({director.nationality})"
                    message += "\n"
                if len(result.directors) > 5:
                    message += f"... and {len(result.directors) - 5} more\n"
            
            if result.address:
                # Truncate long addresses
                address = result.address[:200] + "..." if len(result.address) > 200 else result.address
                message += f"\n*Address:* {address}\n"
            
            # Add buttons for each result
            result_keyboard = []
            
            # Add "Get Full Details" button if details not fetched yet
            if not result.directors:
                result_keyboard.append([
                    InlineKeyboardButton("📄 Get Full Details", callback_data=f"details_{i-1}")
                ])
            
            # Add export button to last result
            if i == len(results):
                result_keyboard.append([InlineKeyboardButton("📥 Export to CSV", callback_data="export_last")])
                result_keyboard.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="menu_main")])
            
            # Send the message with appropriate keyboard
            if result_keyboard:
                await status_message.reply_text(
                    message,
                    parse_mode='Markdown',
                    reply_markup=InlineKeyboardMarkup(result_keyboard)
                )
            else:
                await status_message.reply_text(message, parse_mode='Markdown')
        
        logger.info(f"Successfully sent {len(results)} results to user {user_id}")
    
    except asyncio.TimeoutError:
        logger.error(f"Search timed out after 120 seconds for query: {search_term}")
        await status_message.edit_text(
            "⏰ *Search Timed Out*\n\n"
            "The search took too long to complete.\n\n"
            "*Possible reasons:*\n"
            "• The new MOC website structure may have changed\n"
            "• Heavy traffic on the MOC website\n"
            "• Network connectivity issues\n\n"
            "*What to try:*\n"
            "• Try a different search term\n"
            "• Wait a few minutes and try again\n"
            "• Contact support if the issue persists",
            parse_mode='Markdown',
            reply_markup=get_main_menu_keyboard()
        )
    
    except Exception as e:
        logger.error(f"Error during search: {e}", exc_info=True)
        await status_message.edit_text(
            "❌ *Error occurred during search*\n\n"
            "The search service may be temporarily unavailable. "
            "Please try again in a few moments.\n\n"
            f"Error: `{str(e)[:100]}`",
            parse_mode='Markdown',
            reply_markup=get_main_menu_keyboard()
        )
    
    finally:
        # Clean up active search and decrement counter
        if user_id in active_searches:
            search_info = active_searches[user_id]
            username = search_info.get('username', f'User_{user_id}')
            concurrent_searches = max(0, concurrent_searches - 1)  # Ensure it doesn't go negative
            del active_searches[user_id]
            logger.info(f"🏁 User {username} ({user_id}) search completed | Active searches: {concurrent_searches}/{MAX_CONCURRENT_SEARCHES}")


async def perform_director_search(update: Update, context: ContextTypes.DEFAULT_TYPE, search_term: str):
    """Perform director search via API."""
    global concurrent_searches
    
    user_id = update.effective_user.id
    username = update.effective_user.username or f"User_{user_id}"
    
    if user_id in active_searches:
        msg = "❌ You already have an active search. Please wait or cancel it first."
        if update.callback_query:
            await update.callback_query.answer(msg, show_alert=True)
        else:
            await update.message.reply_text(msg, reply_markup=get_main_menu_keyboard())
        return
    
    if concurrent_searches >= MAX_CONCURRENT_SEARCHES:
        await update.message.reply_text(f"🚦 *System Busy*\n\nPlease try again later.", parse_mode='Markdown', reply_markup=get_main_menu_keyboard())
        return
    
    db.update_user_activity(user_id)
    if db.is_blocked(user_id):
        await update.message.reply_text("❌ You have been blocked from using this bot.")
        return
    
    db.log_interaction(user_id, 'search_director', message_text=search_term)
    
    cancel_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel Search", callback_data=f"cancel_search_{user_id}")]
    ])
    
    if update.callback_query:
        status_message = await update.callback_query.message.reply_text(
            f"👤 Searching for director: *{search_term}*\n\nPlease wait...",
            parse_mode='Markdown', reply_markup=cancel_keyboard
        )
    else:
        status_message = await update.message.reply_text(
            f"👤 Searching for director: *{search_term}*\n\nPlease wait...",
            parse_mode='Markdown', reply_markup=cancel_keyboard
        )
    
    concurrent_searches += 1
    active_searches[user_id] = {'search_term': search_term, 'status_message': status_message, 'cancelled': False, 'username': username, 'start_time': datetime.now()}
    
    try:
        loop = asyncio.get_event_loop()
        start_time = __import__('time').time()
        
        def run_director_search():
            if user_id in active_searches and active_searches[user_id]['cancelled']:
                return None
            try:
                with httpx.Client(timeout=60) as client:
                    resp = client.post(
                        f"{API_BASE_URL}/api/v1/search/director",
                        json={"director_name": search_term, "use_cache": True},
                        headers={"X-API-Key": API_KEY},
                    )
                    data = resp.json()
                    if data.get("success"):
                        return data.get("results", [])
                    return []
            except Exception as e:
                logger.error(f"API director search error: {e}", exc_info=True)
                return []
        
        results = await asyncio.wait_for(loop.run_in_executor(executor, run_director_search), timeout=75.0)
        search_duration = __import__('time').time() - start_time
        
        if not results:
            await status_message.edit_text(
                f"❌ No directors found for: *{search_term}*",
                parse_mode='Markdown', reply_markup=get_main_menu_keyboard()
            )
            return
        
        await status_message.edit_text(
            f"✅ Found *{len(results)}* director result(s) for: *{search_term}*",
            parse_mode='Markdown'
        )
        
        # Store director results for export
        if user_id not in user_search_history:
            user_search_history[user_id] = []
        user_search_history[user_id].append({
            'search_term': search_term,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'results_count': len(results),
            'results': results,
            'search_type': 'director'  # Mark as director search for export
        })
        if len(user_search_history[user_id]) > 20:
            user_search_history[user_id] = user_search_history[user_id][-20:]
        
        for i, person in enumerate(results, 1):
            person_name = person.get('person_name', 'Unknown')
            companies = person.get('companies', [])
            
            MAX_PER_MSG = 50  # Companies per message to stay under Telegram's 4096 limit
            chunks = [companies[j:j+MAX_PER_MSG] for j in range(0, len(companies), MAX_PER_MSG)]
            
            for chunk_idx, chunk in enumerate(chunks):
                if chunk_idx == 0:
                    msg = f"*👤 Director Result {i}/{len(results)}*\n\n"
                    msg += f"*Name:* {person_name}\n"
                    msg += f"*Companies ({len(companies)}):*\n"
                else:
                    msg = f"*{person_name} (continued {chunk_idx + 1}/{len(chunks)}):*\n"
                
                for j, comp in enumerate(chunk, 1 + chunk_idx * MAX_PER_MSG):
                    msg += f"  {j}. *{comp.get('company_name', 'N/A')}*\n"
                    msg += f"     Reg#: `{comp.get('registration_number', 'N/A')}`\n"
                    msg += f"     Role: {comp.get('position', 'N/A')}\n"
                
                kb = [[InlineKeyboardButton("🔙 Back to Menu", callback_data="menu_main")]]
                await status_message.reply_text(msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb) if chunk_idx == len(chunks) - 1 else None)
    
    except Exception as e:
        logger.error(f"Director search error: {e}", exc_info=True)
        await status_message.edit_text(f"❌ Error: {str(e)[:100]}", reply_markup=get_main_menu_keyboard())
    
    finally:
        if user_id in active_searches:
            concurrent_searches = max(0, concurrent_searches - 1)
            del active_searches[user_id]
            logger.info(f"🏁 Director search for {username} completed")


async def cancel_search(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Cancel an active search for a user."""
    global concurrent_searches
    
    if user_id not in active_searches:
        await update.callback_query.answer("❌ No active search to cancel", show_alert=True)
        return
    
    # Mark search as cancelled
    active_searches[user_id]['cancelled'] = True
    search_term = active_searches[user_id]['search_term']
    status_message = active_searches[user_id]['status_message']
    username = active_searches[user_id].get('username', f'User_{user_id}')
    
    # Update the status message
    await status_message.edit_text(
        f"❌ *Search Cancelled*\n\n"
        f"Search for: *{search_term}*\n\n"
        "The search has been cancelled by your request.",
        parse_mode='Markdown',
        reply_markup=get_main_menu_keyboard()
    )
    
    # Clean up and decrement counter
    concurrent_searches = max(0, concurrent_searches - 1)
    del active_searches[user_id]
    
    await update.callback_query.answer("✅ Search cancelled successfully")
    logger.info(f"❌ User {username} ({user_id}) cancelled search for: {search_term} | Active searches: {concurrent_searches}/{MAX_CONCURRENT_SEARCHES}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle regular text messages as search queries."""
    search_term = update.message.text.strip()
    
    # Check if user is in director search mode
    if context.user_data.get('search_mode') == 'director':
        context.user_data['search_mode'] = 'company'  # Reset after use
        await perform_director_search(update, context, search_term)
    else:
        await perform_search(update, context, search_term)


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks."""
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    user_id = query.from_user.id
    
    # Update user activity
    db.update_user_activity(user_id)
    db.log_interaction(user_id, 'callback', callback_data=callback_data)
    
    if callback_data == "menu_main":
        # Show main menu
        await query.edit_message_text(
            "🏢 *Main Menu*\n\nChoose an option below:",
            parse_mode='Markdown',
            reply_markup=get_main_menu_keyboard()
        )
    
    elif callback_data == "admin_menu":
        # Show admin menu
        if db.is_admin(user_id):
            await query.edit_message_text(
                "🔐 *Admin Panel*\n\nChoose an option below:",
                parse_mode='Markdown',
                reply_markup=get_admin_menu_keyboard()
            )
        else:
            await query.edit_message_text("❌ Access denied")
    
    elif callback_data == "admin_stats":
        await admin_stats(update, context)
    
    elif callback_data == "admin_users":
        await admin_users(update, context)
    
    elif callback_data == "admin_broadcast":
        await admin_broadcast_menu(update, context)
    
    elif callback_data == "admin_logs":
        await admin_logs(update, context)
    
    elif callback_data == "admin_search_history":
        await admin_search_history(update, context)
    
    elif callback_data == "admin_db_info":
        await admin_db_info(update, context)
    
    elif callback_data.startswith("cancel_search_"):
        # Handle search cancellation
        try:
            cancel_user_id = int(callback_data.split("_")[-1])
            if cancel_user_id == user_id:  # Only allow users to cancel their own searches
                await cancel_search(update, context, user_id)
            else:
                await query.answer("❌ You can only cancel your own searches", show_alert=True)
        except (ValueError, IndexError):
            await query.answer("❌ Invalid cancel request", show_alert=True)
    
    elif callback_data == "menu_search":
        # Reset mode to company and prompt
        context.user_data['search_mode'] = 'company'
        await query.edit_message_text(
            "🔍 *Search Company*\n\n"
            "Please type the company name you want to search for.\n\n"
            "*Examples:*\n"
            "• ACLEDA\n"
            "• AEON\n"
            "• ABA\n\n"
            "Just type the name and send!",
            parse_mode='Markdown',
            reply_markup=get_back_keyboard()
        )
    
    elif callback_data == "menu_search_director":
        # Set director search mode and prompt
        context.user_data['search_mode'] = 'director'
        await query.edit_message_text(
            "👤 *Search Director*\n\n"
            "Please type the director or person name you want to search for.\n\n"
            "*Examples:*\n"
            "• John Doe\n"
            "• Michael Chen\n"
            "• សុផា មាន\n\n"
            "Just type the name and send!",
            parse_mode='Markdown',
            reply_markup=get_back_keyboard()
        )
    
    elif callback_data == "menu_export":
        # Show export options
        await query.edit_message_text(
            "📊 *Export Options*\n\n"
            "Export your search results to CSV format.\n\n"
            "Click below to export your last search:",
            parse_mode='Markdown',
            reply_markup=get_export_keyboard()
        )
    
    elif callback_data == "menu_history":
        # Show history
        await history_command(update, context)
    
    elif callback_data == "menu_help":
        # Show help
        await help_command(update, context)
    
    elif callback_data == "menu_about":
        # Show about
        await about_command(update, context)
    
    elif callback_data == "export_last":
        # Export last search
        await export_command(update, context)
    
    elif callback_data.startswith("export_details_"):
        # Export detailed information for a specific result
        try:
            result_index = int(callback_data.split("_")[2])
            user_id = query.from_user.id
            
            # Get the result from history
            if user_id not in user_search_history or not user_search_history[user_id]:
                await query.answer("❌ No search history found", show_alert=True)
                return
            
            last_search = user_search_history[user_id][-1]
            results = last_search.get('results', [])
            
            if result_index >= len(results):
                await query.answer("❌ Result not found", show_alert=True)
                return
            
            result = results[result_index]
            
            # Show processing message
            await query.answer("📥 Generating CSV file...", show_alert=False)
            
            # Create CSV in memory
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write headers
            writer.writerow(SearchResult.csv_headers())
            
            # Write the single result
            writer.writerow(result.to_csv_row())
            
            # Get CSV content
            csv_content = output.getvalue()
            output.close()
            
            # Create file object
            csv_file = io.BytesIO(csv_content.encode('utf-8-sig'))
            csv_file.name = f"{result.entity_name.replace(' ', '_')[:30]}_details.csv"
            
            # Send file
            caption = f"📊 *Detailed Export*\n\nCompany: `{result.entity_name}`\nRegistration #: `{result.registration_number}`\nDate: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            
            await query.message.reply_document(
                document=csv_file,
                filename=csv_file.name,
                caption=caption,
                parse_mode='Markdown'
            )
            
            logger.info(f"Exported details for {result.entity_name} to user {user_id}")
        
        except Exception as e:
            logger.error(f"Error exporting details: {e}", exc_info=True)
            await query.answer(f"❌ Error: {str(e)[:50]}", show_alert=True)
    
    elif callback_data.startswith("details_"):
        # Fetch detailed information for a specific result
        try:
            result_index = int(callback_data.split("_")[1])
            user_id = query.from_user.id
            
            # Get the result from history
            if user_id not in user_search_history or not user_search_history[user_id]:
                await query.edit_message_text(
                    "❌ No search history found. Please perform a search first.",
                    parse_mode='Markdown',
                    reply_markup=get_main_menu_keyboard()
                )
                return
            
            last_search = user_search_history[user_id][-1]
            results = last_search.get('results', [])
            
            if result_index >= len(results):
                await query.edit_message_text(
                    "❌ Result not found.",
                    parse_mode='Markdown',
                    reply_markup=get_main_menu_keyboard()
                )
                return
            
            result = results[result_index]
            
            # Show loading message
            await query.edit_message_text(
                f"⏳ Fetching detailed information for:\n*{result.entity_name}*\n\nThis may take a moment...",
                parse_mode='Markdown'
            )
            
            # Fetch details in thread pool using stealth scraper
            loop = asyncio.get_event_loop()
            
            def fetch_details_api():
                try:
                    with httpx.Client(timeout=60) as client:
                        resp = client.post(
                            f"{API_BASE_URL}/api/v1/company/details",
                            json={
                                "registration_number": result.registration_number,
                                "entity_name": result.entity_name,
                                "original_id": result.original_id,
                                "fetch_if_missing": True
                            },
                            headers={"X-API-Key": API_KEY},
                        )
                        data = resp.json()
                        if data.get("success"):
                            return SearchResult({
                                "entity_name": data.get("entity_name", result.entity_name),
                                "entity_name_khmer": data.get("entity_name_khmer", ""),
                                "registration_number": data.get("registration_number", result.registration_number),
                                "original_id": data.get("original_id", ""),
                                "status": data.get("status", ""),
                                "registration_date": data.get("registration_date", ""),
                                "re_registration_date": data.get("re_registration_date", ""),
                                "entity_type": data.get("entity_type", ""),
                                "tin": data.get("tin", ""),
                                "tax_registration_date": data.get("tax_registration_date", ""),
                                "annual_return_date": data.get("annual_return_date", ""),
                                "address": data.get("address", ""),
                                "directors": data.get("directors", [])
                            })
                        return result
                except Exception as e:
                    logger.error(f"API details error: {e}", exc_info=True)
                    return result

            detailed_result = await loop.run_in_executor(
                executor,
                fetch_details_api
            )
            
            # Update the result in history
            results[result_index] = detailed_result
            
            # Format detailed message
            message = f"*📋 Detailed Information*\n\n"
            message += f"*Company (EN):* {detailed_result.entity_name}\n"
            
            if detailed_result.entity_name_khmer:
                message += f"*Company (KH):* {detailed_result.entity_name_khmer}\n"
            
            message += f"*Registration #:* `{detailed_result.registration_number}`\n"
            
            if detailed_result.original_id:
                message += f"*Original ID:* {detailed_result.original_id}\n"
            
            if detailed_result.status:
                message += f"*Status:* {detailed_result.status}\n"
            
            if detailed_result.registration_date:
                message += f"*Incorporation Date:* {detailed_result.registration_date}\n"
            
            if detailed_result.re_registration_date:
                message += f"*Re-Registration Date:* {detailed_result.re_registration_date}\n"
            
            if detailed_result.entity_type:
                message += f"*Type:* {detailed_result.entity_type}\n"
            
            if detailed_result.tin:
                message += f"*TIN:* {detailed_result.tin}\n"
            
            if detailed_result.tax_registration_date:
                message += f"*Tax Reg. Date:* {detailed_result.tax_registration_date}\n"
            
            if detailed_result.annual_return_date:
                message += f"*Annual Return:* {detailed_result.annual_return_date}\n"
            
            if detailed_result.directors:
                # Separate current and former directors
                current_directors = [d for d in detailed_result.directors if not d.is_former]
                former_directors = [d for d in detailed_result.directors if d.is_former]
                
                # Check if there's a chairman
                has_chairman = any(d.is_chairman for d in current_directors)
                message += f"\n*Chairman of the Board:* {'Yes' if has_chairman else 'No'}\n"
                
                # Display current directors
                if current_directors:
                    message += f"\n*👔 Current Directors ({len(current_directors)}):*\n"
                    for j, director in enumerate(current_directors, 1):
                        chairman_mark = " 👑" if director.is_chairman else ""
                        message += f"\n{j}. *{director.name}*{chairman_mark}\n"
                        if director.position:
                            message += f"   Position: {director.position}\n"
                        if director.is_chairman:
                            message += f"   Chairman: Yes\n"
                        if director.nationality:
                            message += f"   Nationality: {director.nationality}\n"
                        if director.appointment_date:
                            message += f"   Appointed: {director.appointment_date}\n"
                
                # Display former directors
                if former_directors:
                    message += f"\n*📋 Former Directors ({len(former_directors)}):*\n"
                    for j, director in enumerate(former_directors, 1):
                        chairman_mark = " 👑" if director.is_chairman else ""
                        message += f"\n{j}. *{director.name}*{chairman_mark}\n"
                        if director.position:
                            message += f"   Position: {director.position}\n"
                        if director.is_chairman:
                            message += f"   Was Chairman: Yes\n"
                        if director.ceased_date:
                            message += f"   Ceased: {director.ceased_date}\n"
                        if director.nationality:
                            message += f"   Nationality: {director.nationality}\n"
                        if director.appointment_date:
                            message += f"   Appointed: {director.appointment_date}\n"
            
            if detailed_result.address:
                address = detailed_result.address[:300] + "..." if len(detailed_result.address) > 300 else detailed_result.address
                message += f"\n*Address:* {address}\n"
            
            # Add buttons: Export Details and Back to Menu
            keyboard = [
                [
                    InlineKeyboardButton("📥 Export Details", callback_data=f"export_details_{result_index}"),
                    InlineKeyboardButton("🔙 Back to Menu", callback_data="menu_main")
                ]
            ]
            
            await query.edit_message_text(
                message,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            logger.info(f"Fetched detailed info for user {user_id}")
        
        except Exception as e:
            logger.error(f"Error fetching details: {e}", exc_info=True)
            await query.edit_message_text(
                f"❌ Error fetching details: {str(e)[:100]}",
                parse_mode='Markdown',
                reply_markup=get_main_menu_keyboard()
            )


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors caused by updates."""
    logger.error(f"Update {update} caused error {context.error}")


async def post_init(application: Application):
    """Set bot commands in Telegram menu."""
    commands = [
        BotCommand("start", "🏠 Start the bot and show main menu"),
        BotCommand("search", "🔍 Search for a company"),
        BotCommand("sd", "👤 Search for a director"),
        BotCommand("export", "📥 Export last search to CSV"),
        BotCommand("history", "📜 View your search history"),
        BotCommand("help", "❓ Show help information"),
        BotCommand("about", "ℹ️ About this bot"),
        BotCommand("admin", "🔐 Admin panel (admins only)"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Bot commands registered in menu")


def main():
    """Start the bot."""
    # Check if token is set
    if BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
        print("❌ Error: Please set TELEGRAM_BOT_TOKEN environment variable")
        print("\nOn Windows:")
        print('  set TELEGRAM_BOT_TOKEN=your_token_here')
        print("\nOn Linux/Mac:")
        print('  export TELEGRAM_BOT_TOKEN=your_token_here')
        sys.exit(1)
    
    # Start health check server for Koyeb/Render
    port = int(os.getenv('PORT', 10000))
    start_health_server(port)
    logger.info(f"Health check server running on port {port}")
    
    # Start keep-alive service if on Render
    render_service = os.getenv('RENDER_SERVICE_NAME')
    if render_service:
        print("🔍 Render deployment detected - starting with keep-alive")
        print("🔄 Starting keep-alive service...")
        
        # Import and start keep-alive service
        try:
            # Add the parent directory to Python path to find keep_alive.py
            import sys
            parent_dir = os.path.dirname(os.path.dirname(__file__))  # Go up from /app/bot/ to /app/
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            logger.info(f"Looking for keep_alive module in: {parent_dir}")
            
            from keep_alive import run_keep_alive_thread
            
            # Get bot URL from environment
            bot_url = os.getenv('BOT_URL', 'https://mocbot.onrender.com')
            
            # Start keep-alive in a separate thread
            keep_alive, thread = run_keep_alive_thread(bot_url)
            logger.info(f"🚀 Keep-alive service started for {bot_url}/health")
            
        except ImportError as e:
            logger.warning(f"Direct keep-alive import failed: {e}")
            # Try alternative approach using standalone service
            try:
                from standalone_keepalive import KeepAliveService
                import threading
                
                bot_url = os.getenv('BOT_URL', 'https://bizsearch.up.railway.app')
                service = KeepAliveService(bot_url)
                service.start()
                logger.info(f"🚀 Standalone keep-alive service started for {bot_url}/health")
                
            except Exception as e2:
                logger.warning(f"Keep-alive service not available: {e2} - bot may sleep on Render")
        except Exception as e:
            logger.warning(f"Keep-alive service error: {e} - bot may sleep on Render")
    
    print("🤖 Starting Telegram bot...")
    
    # Create the Application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Store database in bot_data for access in handlers
    application.bot_data['database'] = db
    
    # Register post_init to set commands
    application.post_init = post_init
    
    # Register command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("about", about_command))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("sd", search_director_command))
    application.add_handler(CommandHandler("history", history_command))
    application.add_handler(CommandHandler("export", export_command))
    
    # Register admin command handlers
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CommandHandler("broadcast", lambda u, c: broadcast_command(u, c, 'all')))
    application.add_handler(CommandHandler("broadcast_active", lambda u, c: broadcast_command(u, c, 'active')))
    application.add_handler(CommandHandler("setadmin", setadmin_command))
    application.add_handler(CommandHandler("removeadmin", removeadmin_command))
    application.add_handler(CommandHandler("block", block_command))
    application.add_handler(CommandHandler("unblock", unblock_command))
    application.add_handler(CommandHandler("userinfo", userinfo_command))
    
    # Register callback query handler for buttons
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Register message handler for direct search
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Register error handler
    application.add_error_handler(error_handler)
    
    # Start the bot
    logger.info("🤖 Bot started successfully!")
    print("🤖 Cambodia MOC Business Registry Bot is running...")
    print(f"Health check available at http://0.0.0.0:{port}/health")
    print("Press Ctrl+C to stop")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    # Fix for Python 3.14+ asyncio event loop issue
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    
    main()
