import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.request import HTTPXRequest
from datetime import datetime
import os
import sqlite3
import time
from functools import wraps

# ============ CONFIGURATION ============

BOT_TOKEN = "8828883232:AAHm3XnCehecaRG_2CsGZKDsa96RTuDZG20"
BOT_USERNAME = "CasinoIndia2026_bot"

# Admin
ADMIN_USER_ID = 5943318266
ADMIN_USERNAME = "@XTOP_879"

# Admin UPI Details (for INR withdrawals)
ADMIN_UPI_ID = "praveennnnguru@fam"
ADMIN_UPI_NAME = "Praveen Kumar"

# ============ PAYMENT LIMITS ============

# INR Limits (in paise)
INR_MIN_DEPOSIT = 10000  # ₹100
INR_MAX_DEPOSIT = 500000  # ₹5,000
INR_MIN_WITHDRAW = 10000  # ₹100
INR_MAX_WITHDRAW = 500000  # ₹5,000

# USD Limits (in cents)
USD_MIN_DEPOSIT = 10  # $0.10
USD_MAX_DEPOSIT = 2000  # $20
USD_MIN_WITHDRAW = 10  # $0.10
USD_MAX_WITHDRAW = 2000  # $20

# ============ PAYMENT DETAILS ============

# INR Payment Methods
INR_PAYMENT = {
    'upi': {
        'id': 'praveennnnguru@fam',
        'name': 'Praveen Kumar',
        'qr_image': 'upi_qr.jpg',
    },
    'bank': {
        'bank': 'State Bank of India',
        'account': '1234567890',
        'ifsc': 'SBIN0001234',
        'name': 'Praveen Kumar',
        'qr_image': 'bank_qr.jpg',
    }
}

# USD Payment Methods
USD_PAYMENT = {
    'crypto': {
        'address': '0xa67269096f6b38Ae7F26a4f093b690820Dde7671',
        'network': 'BEP20',
        'currency': 'USDT',
        'qr_image': 'usdt_qr.jpg',
    }
}

# Database
DB_PATH = "payment_bot.db"

# Payment Success Image Path
PAYMENT_SUCCESS_IMAGE = "payment_success.jpg"  # Save this image in the bot folder

# ============ LOGGING ============

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============ DATABASE HELPER WITH RETRY ============

def get_db():
    """Get database connection with timeout and retry"""
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn

def retry_on_lock(max_retries=5, delay=0.5):
    """Decorator to retry on database lock"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except sqlite3.OperationalError as e:
                    if "database is locked" in str(e) and attempt < max_retries - 1:
                        time.sleep(delay * (attempt + 1))
                        continue
                    raise
            return None
        return wrapper
    return decorator

# ============ HELPER FUNCTIONS ============

def get_qr_image_path(image_name):
    if os.path.exists(image_name):
        return image_name
    qr_folder = "qr_codes"
    if not os.path.exists(qr_folder):
        os.makedirs(qr_folder)
    qr_path = os.path.join(qr_folder, image_name)
    if os.path.exists(qr_path):
        return qr_path
    return None

def format_currency(amount, currency='INR'):
    symbol = '₹' if currency == 'INR' else '$'
    if currency == 'USD':
        return f"{symbol}{amount/100:.2f}"
    return f"{symbol}{amount/100:.2f}"

def parse_amount(amount_str, currency='INR'):
    try:
        if currency == 'USD':
            amount = float(amount_str)
            return int(amount * 100)
        else:
            return int(float(amount_str)) * 100
    except ValueError:
        return None

# ============ DATABASE ============

def init_db():
    conn = get_db()
    c = conn.cursor()
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            currency TEXT DEFAULT 'INR',
            coins INTEGER DEFAULT 100,
            wallet_balance_inr INTEGER DEFAULT 0,
            wallet_balance_usd INTEGER DEFAULT 0,
            total_games INTEGER DEFAULT 0,
            total_wins INTEGER DEFAULT 0,
            total_losses INTEGER DEFAULT 0,
            total_draws INTEGER DEFAULT 0,
            rating INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            experience INTEGER DEFAULT 0,
            referral_code TEXT,
            daily_bonus_claimed TIMESTAMP,
            daily_bonus_streak INTEGER DEFAULT 0,
            total_deposited_inr INTEGER DEFAULT 0,
            total_deposited_usd INTEGER DEFAULT 0,
            total_withdrawn_inr INTEGER DEFAULT 0,
            total_withdrawn_usd INTEGER DEFAULT 0,
            total_won_inr INTEGER DEFAULT 0,
            total_won_usd INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS deposit_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            amount INTEGER,
            currency TEXT,
            method TEXT,
            screenshot TEXT,
            status TEXT DEFAULT 'pending',
            admin_notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMP
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS withdraw_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            amount INTEGER,
            currency TEXT,
            method TEXT,
            upi_id TEXT,
            bank_name TEXT,
            account_number TEXT,
            ifsc_code TEXT,
            crypto_address TEXT,
            crypto_network TEXT,
            status TEXT DEFAULT 'pending',
            admin_notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMP
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT,
            amount INTEGER,
            currency TEXT,
            balance_after INTEGER,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

# ============ USER FUNCTIONS ============

def get_or_create_user(user_id, username, first_name, last_name=None):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = c.fetchone()
    
    if not user:
        username = username if username else f"user_{user_id}"
        first_name = first_name if first_name else "User"
        last_name = last_name if last_name else ""
        
        c.execute('''
            INSERT INTO users (user_id, username, first_name, last_name, referral_code, wallet_balance_inr, wallet_balance_usd)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, username, first_name, last_name, 'REF' + str(user_id)[:5], 0, 0))
        conn.commit()
    
    conn.close()

def get_user_profile(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = c.fetchone()
    conn.close()
    
    if user:
        return {
            'user_id': user[0],
            'username': user[1] or f"User{user[0]}",
            'first_name': user[2] or "User",
            'last_name': user[3] or "",
            'currency': user[4] or 'INR',
            'coins': user[5] or 0,
            'wallet_balance_inr': user[6] or 0,
            'wallet_balance_usd': user[7] or 0,
            'total_games': user[8] or 0,
            'total_wins': user[9] or 0,
            'total_losses': user[10] or 0,
            'total_draws': user[11] or 0,
            'rating': user[12] or 0,
            'level': user[13] or 1,
            'experience': user[14] or 0,
            'referral_code': user[15] or '',
            'daily_bonus_claimed': user[16] if len(user) > 16 else None,
            'daily_bonus_streak': user[17] if len(user) > 17 else 0,
            'total_deposited_inr': user[18] if len(user) > 18 else 0,
            'total_deposited_usd': user[19] if len(user) > 19 else 0,
            'total_withdrawn_inr': user[20] if len(user) > 20 else 0,
            'total_withdrawn_usd': user[21] if len(user) > 21 else 0,
            'total_won_inr': user[22] if len(user) > 22 else 0,
            'total_won_usd': user[23] if len(user) > 23 else 0,
            'created_at': user[24] if len(user) > 24 else None
        }
    return None

def get_user_currency(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT currency FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else 'INR'

def set_user_currency(user_id, currency):
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE users SET currency = ? WHERE user_id = ?', (currency, user_id))
    conn.commit()
    conn.close()

def get_user_balance(user_id, currency='INR'):
    conn = get_db()
    c = conn.cursor()
    if currency == 'INR':
        c.execute('SELECT wallet_balance_inr FROM users WHERE user_id = ?', (user_id,))
    else:
        c.execute('SELECT wallet_balance_usd FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else 0

@retry_on_lock(max_retries=5, delay=0.5)
def update_wallet(user_id, amount, currency='INR'):
    conn = get_db()
    c = conn.cursor()
    try:
        if currency == 'INR':
            c.execute('UPDATE users SET wallet_balance_inr = wallet_balance_inr + ? WHERE user_id = ?', (amount, user_id))
        else:
            c.execute('UPDATE users SET wallet_balance_usd = wallet_balance_usd + ? WHERE user_id = ?', (amount, user_id))
        conn.commit()
        conn.close()
    except Exception as e:
        conn.rollback()
        conn.close()
        raise e

@retry_on_lock(max_retries=5, delay=0.5)
def add_transaction(user_id, type, amount, currency, balance_after, description):
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute('''
            INSERT INTO transactions (user_id, type, amount, currency, balance_after, description)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, type, amount, currency, balance_after, description))
        conn.commit()
        conn.close()
    except Exception as e:
        conn.rollback()
        conn.close()
        raise e

def create_deposit_request(user_id, username, amount, currency, method, screenshot):
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        INSERT INTO deposit_requests (user_id, username, amount, currency, method, screenshot)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, username or str(user_id), amount, currency, method, screenshot))
    conn.commit()
    conn.close()

def create_withdraw_request(user_id, username, amount, currency, method, upi_id=None, bank_name=None, account_number=None, ifsc_code=None, crypto_address=None, crypto_network=None):
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        INSERT INTO withdraw_requests 
        (user_id, username, amount, currency, method, upi_id, bank_name, account_number, ifsc_code, crypto_address, crypto_network)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, username or str(user_id), amount, currency, method, upi_id, bank_name, account_number, ifsc_code, crypto_address, crypto_network))
    conn.commit()
    conn.close()

def get_deposit_history(user_id, limit=20):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM deposit_requests WHERE user_id = ? ORDER BY created_at DESC LIMIT ?', (user_id, limit))
    result = c.fetchall()
    conn.close()
    return result

def get_withdraw_history(user_id, limit=20):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM withdraw_requests WHERE user_id = ? ORDER BY created_at DESC LIMIT ?', (user_id, limit))
    result = c.fetchall()
    conn.close()
    return result

def get_transactions(user_id, limit=20):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM transactions WHERE user_id = ? ORDER BY created_at DESC LIMIT ?', (user_id, limit))
    result = c.fetchall()
    conn.close()
    return result

def get_pending_deposits():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM deposit_requests WHERE status = "pending" ORDER BY created_at DESC')
    result = c.fetchall()
    conn.close()
    return result

def get_pending_withdrawals():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM withdraw_requests WHERE status = "pending" ORDER BY created_at DESC')
    result = c.fetchall()
    conn.close()
    return result

@retry_on_lock(max_retries=5, delay=0.5)
def approve_deposit(deposit_id):
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute('SELECT * FROM deposit_requests WHERE id = ?', (deposit_id,))
        deposit = c.fetchone()
        
        if not deposit:
            conn.close()
            return False, None
        
        if deposit[7] != 'pending':
            conn.close()
            return False, None
        
        c.execute('UPDATE deposit_requests SET status = "approved", processed_at = CURRENT_TIMESTAMP WHERE id = ?', (deposit_id,))
        user_id = deposit[1]
        amount = deposit[3]
        currency = deposit[4]
        
        if currency == 'INR':
            c.execute('UPDATE users SET wallet_balance_inr = wallet_balance_inr + ? WHERE user_id = ?', (amount, user_id))
            c.execute('UPDATE users SET total_deposited_inr = total_deposited_inr + ? WHERE user_id = ?', (amount, user_id))
        else:
            c.execute('UPDATE users SET wallet_balance_usd = wallet_balance_usd + ? WHERE user_id = ?', (amount, user_id))
            c.execute('UPDATE users SET total_deposited_usd = total_deposited_usd + ? WHERE user_id = ?', (amount, user_id))
        
        balance = get_user_balance(user_id, currency)
        c.execute('''
            INSERT INTO transactions (user_id, type, amount, currency, balance_after, description)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, 'deposit', amount, currency, balance, f"Deposit approved - {deposit[5]}"))
        
        conn.commit()
        conn.close()
        return True, deposit
        
    except Exception as e:
        conn.rollback()
        conn.close()
        raise e

@retry_on_lock(max_retries=5, delay=0.5)
def reject_deposit(deposit_id, reason=None):
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute('SELECT * FROM deposit_requests WHERE id = ?', (deposit_id,))
        deposit = c.fetchone()
        
        if not deposit:
            conn.close()
            return False, None
        
        if deposit[7] != 'pending':
            conn.close()
            return False, None
        
        c.execute('UPDATE deposit_requests SET status = "rejected", processed_at = CURRENT_TIMESTAMP WHERE id = ?', (deposit_id,))
        if reason:
            c.execute('UPDATE deposit_requests SET admin_notes = ? WHERE id = ?', (reason, deposit_id))
        
        conn.commit()
        conn.close()
        return True, deposit
        
    except Exception as e:
        conn.rollback()
        conn.close()
        raise e

@retry_on_lock(max_retries=5, delay=0.5)
def approve_withdrawal(withdraw_id):
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute('SELECT * FROM withdraw_requests WHERE id = ?', (withdraw_id,))
        withdraw = c.fetchone()
        
        if not withdraw:
            conn.close()
            return False, None
        
        if withdraw[12] != 'pending':
            conn.close()
            return False, None
        
        c.execute('UPDATE withdraw_requests SET status = "approved", processed_at = CURRENT_TIMESTAMP WHERE id = ?', (withdraw_id,))
        
        conn.commit()
        conn.close()
        return True, withdraw
        
    except Exception as e:
        conn.rollback()
        conn.close()
        raise e

@retry_on_lock(max_retries=5, delay=0.5)
def complete_withdrawal(withdraw_id):
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute('SELECT * FROM withdraw_requests WHERE id = ?', (withdraw_id,))
        withdraw = c.fetchone()
        
        if not withdraw:
            conn.close()
            return False, None
        
        if withdraw[12] == 'completed':
            conn.close()
            return False, None
        
        if withdraw[12] != 'approved':
            conn.close()
            return False, None
        
        c.execute('UPDATE withdraw_requests SET status = "completed", processed_at = CURRENT_TIMESTAMP WHERE id = ?', (withdraw_id,))
        
        user_id = withdraw[1]
        amount = withdraw[3]
        currency = withdraw[4]
        
        balance = get_user_balance(user_id, currency)
        c.execute('''
            INSERT INTO transactions (user_id, type, amount, currency, balance_after, description)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, 'withdraw', -amount, currency, balance, f"Withdraw completed - {withdraw[5]}"))
        
        if currency == 'INR':
            c.execute('UPDATE users SET total_withdrawn_inr = total_withdrawn_inr + ? WHERE user_id = ?', (amount, user_id))
        else:
            c.execute('UPDATE users SET total_withdrawn_usd = total_withdrawn_usd + ? WHERE user_id = ?', (amount, user_id))
        
        c.execute('SELECT * FROM withdraw_requests WHERE id = ?', (withdraw_id,))
        updated_withdraw = c.fetchone()
        
        conn.commit()
        conn.close()
        return True, updated_withdraw
        
    except Exception as e:
        conn.rollback()
        conn.close()
        raise e

@retry_on_lock(max_retries=5, delay=0.5)
def reject_withdrawal(withdraw_id, reason=None):
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute('SELECT * FROM withdraw_requests WHERE id = ?', (withdraw_id,))
        withdraw = c.fetchone()
        
        if not withdraw:
            conn.close()
            return False, None
        
        if withdraw[12] != 'pending':
            conn.close()
            return False, None
        
        user_id = withdraw[1]
        amount = withdraw[3]
        currency = withdraw[4]
        
        if currency == 'INR':
            c.execute('UPDATE users SET wallet_balance_inr = wallet_balance_inr + ? WHERE user_id = ?', (amount, user_id))
        else:
            c.execute('UPDATE users SET wallet_balance_usd = wallet_balance_usd + ? WHERE user_id = ?', (amount, user_id))
        
        c.execute('UPDATE withdraw_requests SET status = "rejected", processed_at = CURRENT_TIMESTAMP WHERE id = ?', (withdraw_id,))
        if reason:
            c.execute('UPDATE withdraw_requests SET admin_notes = ? WHERE id = ?', (reason, withdraw_id))
        
        balance = get_user_balance(user_id, currency)
        c.execute('''
            INSERT INTO transactions (user_id, type, amount, currency, balance_after, description)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, 'withdraw_rejected', amount, currency, balance, f"Withdraw rejected - refunded: {reason or 'No reason'}"))
        
        conn.commit()
        conn.close()
        return True, withdraw
        
    except Exception as e:
        conn.rollback()
        conn.close()
        raise e

def get_all_users():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT user_id, username, first_name, currency, wallet_balance_inr, wallet_balance_usd FROM users ORDER BY user_id DESC')
    result = c.fetchall()
    conn.close()
    return result

# ============ BOT HANDLERS ============

async def payment_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show payment menu directly"""
    user = update.effective_user
    
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        user = query.from_user
        message = query.message
        edit_mode = True
    else:
        message = update.message
        edit_mode = False
    
    username = user.username if user.username else f"user_{user.id}"
    first_name = user.first_name if user.first_name else "User"
    last_name = user.last_name if user.last_name else ""
    
    get_or_create_user(user.id, username, first_name, last_name)
    profile = get_user_profile(user.id)
    
    if not profile:
        await message.reply_text("❌ Error loading profile.")
        return
    
    if not profile['currency']:
        keyboard = [[InlineKeyboardButton("🇮🇳 INR (₹)", callback_data="currency_INR"), InlineKeyboardButton("🇺🇸 USD ($)", callback_data="currency_USD")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await message.reply_text("🌍 Select your currency:", reply_markup=reply_markup)
        return
    
    currency = profile['currency']
    symbol = '₹' if currency == 'INR' else '$'
    balance = get_user_balance(user.id, currency) / 100
    
    if currency == 'INR':
        deposited = profile.get('total_deposited_inr', 0) / 100
        withdrawn = profile.get('total_withdrawn_inr', 0) / 100
        won = profile.get('total_won_inr', 0) / 100
    else:
        deposited = profile.get('total_deposited_usd', 0) / 100
        withdrawn = profile.get('total_withdrawn_usd', 0) / 100
        won = profile.get('total_won_usd', 0) / 100
    
    is_admin = "👑 ADMIN" if user.id == ADMIN_USER_ID else ""
    username_display = f"@{user.username}" if user.username else first_name
    
    if currency == 'INR':
        deposit_limit = f"₹{INR_MIN_DEPOSIT/100:.2f} - ₹{INR_MAX_DEPOSIT/100:.2f}"
        withdraw_limit = f"₹{INR_MIN_WITHDRAW/100:.2f} - ₹{INR_MAX_WITHDRAW/100:.2f}"
    else:
        deposit_limit = f"${USD_MIN_DEPOSIT/100:.2f} - ${USD_MAX_DEPOSIT/100:.2f}"
        withdraw_limit = f"${USD_MIN_WITHDRAW/100:.2f} - ${USD_MAX_WITHDRAW/100:.2f}"
    
    keyboard = [
        [InlineKeyboardButton("📥 Deposit", callback_data="deposit_main"), InlineKeyboardButton("📤 Withdraw", callback_data="withdraw_main")],
        [InlineKeyboardButton("📋 Deposit History", callback_data="deposit_history"), InlineKeyboardButton("📋 Withdraw History", callback_data="withdraw_history")],
        [InlineKeyboardButton("📊 Transactions", callback_data="transactions")],
        [InlineKeyboardButton("🔄 Change Currency", callback_data="change_currency")]
    ]
    
    if is_admin:
        keyboard.append([InlineKeyboardButton("👑 Admin Panel", callback_data="admin_panel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    profile_text = f"""
╔═══════════════════════════════════════╗
║      💳 CASINO INDIA PAYMENT          ║
╠═══════════════════════════════════════╣
║                                       ║
║  👤 {username_display} {is_admin}              ║
║  🆔 ID: {user.id}                              ║
║  🌐 Currency: {currency}                       ║
║                                       ║
║  💰 Balance: {symbol}{balance:.2f}             ║
║  📥 Deposited: {symbol}{deposited:.2f}         ║
║  📤 Withdrawn: {symbol}{withdrawn:.2f}         ║
║  🏆 Won: {symbol}{won:.2f}                    ║
║                                       ║
║  📌 Deposit Limits: {deposit_limit}            ║
║  📌 Withdraw Limits: {withdraw_limit}          ║
║                                       ║
╠═══════════════════════════════════════╣
║  💳 UPI: {ADMIN_UPI_ID}               ║
║  🏦 Bank: SBI                        ║
║  🪙 USDT (BEP20): {USD_PAYMENT['crypto']['address'][:15]}...   ║
╚═══════════════════════════════════════╝
    """
    
    if edit_mode and message:
        await message.edit_text(profile_text, reply_markup=reply_markup)
    else:
        await message.reply_text(profile_text, reply_markup=reply_markup)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await payment_menu(update, context)

# ============ CURRENCY ============

async def set_currency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    currency = query.data.replace('currency_', '')
    user_id = update.effective_user.id
    
    set_user_currency(user_id, currency)
    
    await query.edit_message_text(f"✅ Currency changed to {currency}!")
    await payment_menu(update, context)

# ============ DEPOSIT ============

async def deposit_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    currency = get_user_currency(update.effective_user.id)
    symbol = '₹' if currency == 'INR' else '$'
    
    if currency == 'INR':
        min_display = f"₹{INR_MIN_DEPOSIT/100:.2f}"
        max_display = f"₹{INR_MAX_DEPOSIT/100:.2f}"
    else:
        min_display = f"${USD_MIN_DEPOSIT/100:.2f}"
        max_display = f"${USD_MAX_DEPOSIT/100:.2f}"
    
    keyboard = []
    
    if currency == 'INR':
        keyboard.append([InlineKeyboardButton("📱 UPI Payment", callback_data="deposit_inr_upi")])
        keyboard.append([InlineKeyboardButton("🏦 Bank Transfer", callback_data="deposit_inr_bank")])
    else:
        keyboard.append([InlineKeyboardButton("🪙 USDT (BEP20)", callback_data="deposit_usdt")])
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="payment_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"""
╔═══════════════════════════════════════╗
║      📥 DEPOSIT FUNDS                 ║
╠═══════════════════════════════════════╣
║                                       ║
║  💰 Currency: {currency}                       ║
║  📌 Min: {min_display}                         ║
║  📌 Max: {max_display}                         ║
║                                       ║
╠═══════════════════════════════════════╣
║  Select payment method:               ║
║                                       ║
║  {'' if currency == 'INR' else '🪙 USDT (BEP20) - 10-30 min'}              ║
║  {'' if currency == 'INR' else 'Send USDT to address'}                     ║
║  {'📱 UPI - Instant' if currency == 'INR' else ''}                        ║
║  {'🏦 Bank - 1-2 hours' if currency == 'INR' else ''}                    ║
║                                       ║
║  ⚠️ All deposits verified by admin    ║
║     {ADMIN_USERNAME}                          ║
╚═══════════════════════════════════════╝
        """,
        reply_markup=reply_markup
    )

async def send_payment_details(update, query, title, details, back_callback="deposit_main"):
    keyboard = [
        [InlineKeyboardButton("✅ I've Made Payment", callback_data="deposit_confirm")],
        [InlineKeyboardButton("🔙 Back", callback_data=back_callback)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = f"""
╔═══════════════════════════════════════╗
║      {title}          ║
╠═══════════════════════════════════════╣
║                                       ║
"""
    
    for key, value in details.items():
        if key != 'qr_image':
            text += f"║  {key}: {value}\n"
    
    text += f"""║                                       ║
║  📌 Steps:                            ║
║  1️⃣ Send payment                     ║
║  2️⃣ Click "I've Made Payment"        ║
║  3️⃣ Upload payment screenshot        ║
║  4️⃣ Admin approves {ADMIN_USERNAME}           ║
║                                       ║
║  ⏳ Processing: 15-30 min             ║
║                                       ║
╚═══════════════════════════════════════╝
    """
    
    qr_path = get_qr_image_path(details.get('qr_image', ''))
    
    if qr_path and os.path.exists(qr_path):
        try:
            await query.message.reply_photo(
                photo=open(qr_path, 'rb'),
                caption=text,
                reply_markup=reply_markup
            )
            await query.message.delete()
            return
        except Exception as e:
            logger.error(f"Error sending QR image: {e}")
    
    await query.edit_message_text(text, reply_markup=reply_markup)

async def deposit_inr_upi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    details = {
        '📌 UPI': INR_PAYMENT['upi']['id'],
        '👤 Name': INR_PAYMENT['upi']['name'],
        'qr_image': INR_PAYMENT['upi']['qr_image']
    }
    await send_payment_details(update, query, "📱 UPI DEPOSIT (INR)", details)

async def deposit_inr_bank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    details = {
        '🏦 Bank': INR_PAYMENT['bank']['bank'],
        '📌 Account': INR_PAYMENT['bank']['account'],
        '🔑 IFSC': INR_PAYMENT['bank']['ifsc'],
        '👤 Name': INR_PAYMENT['bank']['name'],
        'qr_image': INR_PAYMENT['bank']['qr_image']
    }
    await send_payment_details(update, query, "🏦 BANK DEPOSIT (INR)", details)

async def deposit_usdt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    details = {
        '📌 Address': USD_PAYMENT['crypto']['address'],
        '🌐 Network': USD_PAYMENT['crypto']['network'],
        '💱 Currency': USD_PAYMENT['crypto']['currency'],
        'qr_image': USD_PAYMENT['crypto']['qr_image']
    }
    await send_payment_details(update, query, "🪙 USDT DEPOSIT (BEP20)", details)

async def deposit_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    username_display = f"@{user.username}" if user.username else user.first_name or "User"
    
    keyboard = [
        [InlineKeyboardButton("🔙 Back", callback_data="deposit_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"""
╔═══════════════════════════════════════╗
║      📸 PAYMENT SCREENSHOT            ║
╠═══════════════════════════════════════╣
║                                       ║
║  Please send the payment screenshot.  ║
║                                       ║
║  Include in your message:             ║
║  • Username: {username_display}              ║
║  • Amount sent                        ║
║  • Payment method                     ║
║                                       ║
║  ⏳ Admin will verify and add balance  ║
║     {ADMIN_USERNAME}                          ║
║                                       ║
║  📤 Send the screenshot now!          ║
║                                       ║
╚═══════════════════════════════════════╝
        """,
        reply_markup=reply_markup
    )
    context.user_data['awaiting_screenshot'] = True

async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = update.effective_user
    
    if not update.message.photo:
        await update.message.reply_text("❌ Please send a screenshot image.")
        return
    
    currency = get_user_currency(user_id)
    username = user.username or str(user_id)
    
    os.makedirs("deposits", exist_ok=True)
    
    photo = update.message.photo[-1]
    file = await photo.get_file()
    file_path = f"deposits/{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    await file.download_to_drive(file_path)
    
    create_deposit_request(user_id, username, 0, currency, "Screenshot", file_path)
    
    await update.message.reply_text(
        f"""
✅ **Screenshot Received!**

📸 Screenshot saved.

⏳ Admin {ADMIN_USERNAME} will verify and add balance.

📌 You will be notified when approved.
        """
    )
    
    username_display = f"@{user.username}" if user.username else user.first_name or "User"
    
    keyboard = [
        [InlineKeyboardButton("✅ Approve", callback_data=f"admin_approve_{user_id}")],
        [InlineKeyboardButton("❌ Reject", callback_data=f"admin_reject_{user_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id FROM deposit_requests WHERE user_id = ? AND status = "pending" ORDER BY created_at DESC LIMIT 1', (user_id,))
    result = c.fetchone()
    conn.close()
    
    deposit_id = result[0] if result else "unknown"
    
    await context.bot.send_photo(
        chat_id=ADMIN_USER_ID,
        photo=open(file_path, 'rb'),
        caption=f"""
📥 **New Deposit Request**

👤 User: {username_display}
🆔 ID: {user_id}
💱 Currency: {currency}
📸 Screenshot: {file_path}
📌 Deposit ID: {deposit_id}

Use: /approve_deposit {deposit_id} [amount]
Use: /reject_deposit {deposit_id} [reason]
        """,
        reply_markup=reply_markup
    )

# ============ ADMIN BUTTON HANDLERS ============

async def admin_approve_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await query.edit_message_text("❌ Unauthorized!")
        return
    
    data = query.data
    target_user_id = int(data.replace('admin_approve_', ''))
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, amount, currency FROM deposit_requests WHERE user_id = ? AND status = "pending" ORDER BY created_at DESC LIMIT 1', (target_user_id,))
    deposit = c.fetchone()
    conn.close()
    
    if not deposit:
        await query.edit_message_text("❌ No pending deposit found for this user!")
        return
    
    deposit_id = deposit[0]
    amount = deposit[1]
    currency = deposit[2]
    
    keyboard = [
        [InlineKeyboardButton("🔙 Cancel", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"""
💰 **Approve Deposit**

Deposit ID: {deposit_id}
User ID: {target_user_id}
Currency: {currency}

📌 Enter amount to approve:
/approve_deposit {deposit_id} [amount]

Example: /approve_deposit {deposit_id} 100
        """,
        reply_markup=reply_markup
    )

async def admin_reject_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await query.edit_message_text("❌ Unauthorized!")
        return
    
    data = query.data
    target_user_id = int(data.replace('admin_reject_', ''))
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, amount, currency FROM deposit_requests WHERE user_id = ? AND status = "pending" ORDER BY created_at DESC LIMIT 1', (target_user_id,))
    deposit = c.fetchone()
    conn.close()
    
    if not deposit:
        await query.edit_message_text("❌ No pending deposit found for this user!")
        return
    
    deposit_id = deposit[0]
    
    keyboard = [
        [InlineKeyboardButton("🔙 Cancel", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"""
❌ **Reject Deposit**

Deposit ID: {deposit_id}
User ID: {target_user_id}

📌 Enter reason:
/reject_deposit {deposit_id} [reason]

Example: /reject_deposit {deposit_id} Invalid screenshot
        """,
        reply_markup=reply_markup
    )

# ============ WITHDRAW ============

async def withdraw_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    currency = get_user_currency(user_id)
    symbol = '₹' if currency == 'INR' else '$'
    balance = get_user_balance(user_id, currency) / 100
    
    if currency == 'INR':
        min_display = f"₹{INR_MIN_WITHDRAW/100:.2f}"
        max_display = f"₹{INR_MAX_WITHDRAW/100:.2f}"
    else:
        min_display = f"${USD_MIN_WITHDRAW/100:.2f}"
        max_display = f"${USD_MAX_WITHDRAW/100:.2f}"
    
    keyboard = []
    
    if currency == 'INR':
        keyboard.append([InlineKeyboardButton("📱 UPI Withdraw", callback_data="withdraw_upi")])
    else:
        keyboard.append([InlineKeyboardButton("🪙 USDT Withdraw", callback_data="withdraw_usdt")])
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="payment_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"""
╔═══════════════════════════════════════╗
║      📤 WITHDRAW FUNDS                ║
╠═══════════════════════════════════════╣
║                                       ║
║  💰 Balance: {symbol}{balance:.2f}             ║
║  📌 Min: {min_display}                         ║
║  📌 Max: {max_display}                         ║
║                                       ║
╠═══════════════════════════════════════╣
║  Select withdrawal method:            ║
║                                       ║
║  {'' if currency == 'INR' else '🪙 USDT (BEP20) - 1-2 hours'}           ║
║  {'' if currency == 'INR' else 'Send USDT to your wallet'}               ║
║  {'📱 UPI - 24-48 hours' if currency == 'INR' else ''}                  ║
║                                       ║
║  ⚠️ All withdrawals verified by admin ║
║     {ADMIN_USERNAME}                          ║
╚═══════════════════════════════════════╝
        """,
        reply_markup=reply_markup
    )

async def withdraw_upi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        f"""
╔═══════════════════════════════════════╗
║      📤 UPI WITHDRAW (INR)           ║
╠═══════════════════════════════════════╣
║                                       ║
║  Format: `/withdraw UPI_ID AMOUNT`    ║
║  Example: `/withdraw {ADMIN_UPI_ID} 100` ║
║                                       ║
║  📌 Requirements:                     ║
║  • Min: ₹{INR_MIN_WITHDRAW/100:.2f}                         ║
║  • Max: ₹{INR_MAX_WITHDRAW/100:.2f}                         ║
║  • UPI ID must be valid              ║
║                                       ║
║  ⏳ Processing: 24-48 hours           ║
║  👑 Admin: {ADMIN_USERNAME}                   ║
║                                       ║
║  💡 Amount will be deducted from      ║
║     your INR wallet balance           ║
╚═══════════════════════════════════════╝
        """
    )

async def withdraw_usdt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        f"""
╔═══════════════════════════════════════╗
║      🪙 USDT WITHDRAW (BEP20)        ║
╠═══════════════════════════════════════╣
║                                       ║
║  Format: `/withdraw_usdt ADDRESS AMOUNT` ║
║  Example: `/withdraw_usdt 0xa67269096f6b38Ae7F26a4f093b690820Dde7671 5.5` ║
║                                       ║
║  📌 Requirements:                     ║
║  • Network: BEP20                    ║
║  • Min: ${USD_MIN_WITHDRAW/100:.2f}                          ║
║  • Max: ${USD_MAX_WITHDRAW/100:.2f}                          ║
║  • Address must be valid             ║
║  • Amount can be decimal (e.g., 5.5) ║
║                                       ║
║  ⏳ Processing: 1-2 hours             ║
║  👑 Admin: {ADMIN_USERNAME}                   ║
║                                       ║
║  💡 Amount will be deducted from      ║
║     your USD wallet balance           ║
╚═══════════════════════════════════════╝
        """
    )

async def withdraw_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if len(context.args) < 2:
        await update.message.reply_text("❌ Usage: /withdraw UPI_ID AMOUNT")
        return
    
    upi_id = context.args[0]
    try:
        amount_input = int(float(context.args[1]) * 100)
    except ValueError:
        await update.message.reply_text("❌ Invalid amount! Please enter a valid number.")
        return
    
    currency = get_user_currency(user_id)
    
    if currency != 'INR':
        await update.message.reply_text("❌ UPI withdrawals are only available for INR currency!\nPlease change your currency to INR or use /withdraw_usdt for USD.")
        return
    
    if amount_input < INR_MIN_WITHDRAW:
        await update.message.reply_text(f"❌ Minimum withdrawal is ₹{INR_MIN_WITHDRAW/100:.2f}")
        return
    
    if amount_input > INR_MAX_WITHDRAW:
        await update.message.reply_text(f"❌ Maximum withdrawal is ₹{INR_MAX_WITHDRAW/100:.2f}")
        return
    
    balance = get_user_balance(user_id, currency)
    
    if balance < amount_input:
        symbol = '₹' if currency == 'INR' else '$'
        await update.message.reply_text(f"❌ Insufficient balance! You have {symbol}{balance/100:.2f}")
        return
    
    update_wallet(user_id, -(amount_input), currency)
    
    user = update.effective_user
    username = user.username or str(user_id)
    
    create_withdraw_request(user_id, username, amount_input, currency, 'UPI', upi_id=upi_id)
    
    symbol = '₹' if currency == 'INR' else '$'
    await update.message.reply_text(
        f"""
✅ **Withdraw Request Created!**

📤 Amount: {symbol}{amount_input/100:.2f}
📱 UPI: {upi_id}
⏳ Status: Pending

📌 Processing: 24-48 hours
📌 Admin will approve and send money
        """
    )
    
    username_display = f"@{user.username}" if user.username else user.first_name or "User"
    await context.bot.send_message(
        chat_id=ADMIN_USER_ID,
        text=f"""
📤 **New INR UPI Withdraw Request**

👤 User: {username_display}
🆔 ID: {user_id}
💰 Amount: {symbol}{amount_input/100:.2f}
💱 Currency: {currency}
📱 UPI: {upi_id}

📌 Use: /approve_withdraw [withdraw_id]
📌 Use: /reject_withdraw [withdraw_id] [reason]
        """
    )

async def withdraw_usdt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if len(context.args) < 2:
        await update.message.reply_text("❌ Usage: /withdraw_usdt ADDRESS AMOUNT\nExample: /withdraw_usdt 0x... 5.5")
        return
    
    crypto_address = context.args[0]
    try:
        amount_float = float(context.args[1])
        amount = int(amount_float * 100)
    except ValueError:
        await update.message.reply_text("❌ Invalid amount! Please enter a valid number.\nExample: 5.5 or 10.25")
        return
    
    currency = get_user_currency(user_id)
    
    if currency != 'USD':
        await update.message.reply_text("❌ USDT withdrawals are only available for USD currency!\nPlease change your currency to USD or use /withdraw for INR.")
        return
    
    if amount < USD_MIN_WITHDRAW:
        await update.message.reply_text(f"❌ Minimum withdrawal is ${USD_MIN_WITHDRAW/100:.2f}")
        return
    
    if amount > USD_MAX_WITHDRAW:
        await update.message.reply_text(f"❌ Maximum withdrawal is ${USD_MAX_WITHDRAW/100:.2f}")
        return
    
    balance = get_user_balance(user_id, currency)
    
    if balance < amount:
        symbol = '₹' if currency == 'INR' else '$'
        await update.message.reply_text(f"❌ Insufficient balance! You have {symbol}{balance/100:.2f}")
        return
    
    update_wallet(user_id, -(amount), currency)
    
    user = update.effective_user
    username = user.username or str(user_id)
    
    create_withdraw_request(user_id, username, amount, currency, 'Crypto', crypto_address=crypto_address, crypto_network='BEP20')
    
    symbol = '₹' if currency == 'INR' else '$'
    await update.message.reply_text(
        f"""
✅ **Withdraw Request Created!**

📤 Amount: {symbol}{amount/100:.2f}
🪙 Address: {crypto_address}
🌐 Network: BEP20
⏳ Status: Pending

📌 Processing: 1-2 hours
📌 Admin will send USDT to your address
        """
    )
    
    username_display = f"@{user.username}" if user.username else user.first_name or "User"
    await context.bot.send_message(
        chat_id=ADMIN_USER_ID,
        text=f"""
📤 **New USD USDT Withdraw Request**

👤 User: {username_display}
🆔 ID: {user_id}
💰 Amount: {symbol}{amount/100:.2f}
💱 Currency: {currency}
🪙 Address: {crypto_address}
🌐 Network: BEP20

📌 Use: /approve_withdraw [withdraw_id]
📌 Use: /reject_withdraw [withdraw_id] [reason]
        """
    )

# ============ HISTORY ============

async def deposit_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    history = get_deposit_history(user_id)
    
    if not history:
        await query.edit_message_text("📋 No deposit history found.")
        return
    
    text = "📋 DEPOSIT HISTORY\n\n"
    for h in history[:10]:
        symbol = '₹' if h[4] == 'INR' else '$'
        status_emoji = {'pending': '⏳', 'approved': '✅', 'rejected': '❌'}.get(h[7], '❓')
        text += f"{status_emoji} {symbol}{h[3]/100:.2f} - {h[5]}\n   📅 {h[9]}\n   Status: {h[7].upper()}\n\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="payment_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup)

async def withdraw_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    history = get_withdraw_history(user_id)
    
    if not history:
        await query.edit_message_text("📋 No withdraw history found.")
        return
    
    text = "📋 WITHDRAW HISTORY\n\n"
    for h in history[:10]:
        symbol = '₹' if h[4] == 'INR' else '$'
        status_emoji = {'pending': '⏳', 'approved': '✅', 'rejected': '❌', 'completed': '🎉'}.get(h[12], '❓')
        text += f"{status_emoji} {symbol}{h[3]/100:.2f} - {h[5]}\n   📅 {h[14]}\n   Status: {h[12].upper()}\n\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="payment_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup)

async def transactions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    history = get_transactions(user_id)
    
    if not history:
        await query.edit_message_text("📊 No transactions found.")
        return
    
    text = "📊 TRANSACTIONS\n\n"
    for h in history[:15]:
        symbol = '₹' if h[3] == 'INR' else '$'
        type_emoji = {'deposit': '📥', 'withdraw': '📤', 'won': '🏆'}.get(h[1], '📊')
        text += f"{type_emoji} {h[1].upper()}\n   Amount: {symbol}{h[2]/100:.2f}\n   Balance: {symbol}{h[4]/100:.2f}\n   📅 {h[6]}\n\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="payment_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup)

# ============ CHANGE CURRENCY ============

async def change_currency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🇮🇳 INR (₹)", callback_data="currency_INR")],
        [InlineKeyboardButton("🇺🇸 USD ($)", callback_data="currency_USD")],
        [InlineKeyboardButton("🔙 Back", callback_data="payment_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"""
🔄 **Change Currency**

Select your preferred currency:

🇮🇳 INR - Indian Rupee
🇺🇸 USD - US Dollar

⚠️ Your wallet balance will remain in the same currency.
Only future transactions will use the new currency.

📌 **Payment Limits:**
🇮🇳 INR: ₹{INR_MIN_DEPOSIT/100:.2f} - ₹{INR_MAX_DEPOSIT/100:.2f}
🇺🇸 USD: ${USD_MIN_DEPOSIT/100:.2f} - ${USD_MAX_DEPOSIT/100:.2f}

Admin: {ADMIN_USERNAME}
        """,
        reply_markup=reply_markup
    )

# ============ ADMIN PANEL ============

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await query.edit_message_text("❌ Unauthorized!")
        return
    
    pending_deposits = get_pending_deposits()
    pending_withdrawals = get_pending_withdrawals()
    
    keyboard = [
        [InlineKeyboardButton(f"📥 Pending Deposits ({len(pending_deposits)})", callback_data="admin_deposits")],
        [InlineKeyboardButton(f"📤 Pending Withdrawals ({len(pending_withdrawals)})", callback_data="admin_withdrawals")],
        [InlineKeyboardButton("💰 Add Balance", callback_data="admin_add_balance")],
        [InlineKeyboardButton("💵 Give All ₹10", callback_data="admin_give_all")],
        [InlineKeyboardButton("📊 All Users", callback_data="admin_users")],
        [InlineKeyboardButton("🔙 Back", callback_data="payment_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"""
╔═══════════════════════════════════════╗
║      👑 ADMIN PANEL                   ║
╠═══════════════════════════════════════╣
║                                       ║
║  Welcome {ADMIN_USERNAME}!            ║
║                                       ║
║  📥 Pending Deposits: {len(pending_deposits)}    ║
║  📤 Pending Withdrawals: {len(pending_withdrawals)} ║
║                                       ║
╠═══════════════════════════════════════╣
║  📥 Click to view pending deposits    ║
║  📤 Click to view pending withdrawals ║
║  💰 Add balance to any user           ║
║  💵 Give ₹10 to ALL users             ║
║  📊 View all users                    ║
╚═══════════════════════════════════════╝
        """,
        reply_markup=reply_markup
    )

async def admin_deposits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await query.edit_message_text("❌ Unauthorized!")
        return
    
    deposits = get_pending_deposits()
    if not deposits:
        await query.edit_message_text("📥 No pending deposits.")
        return
    
    text = "📥 PENDING DEPOSITS\n\n"
    for d in deposits:
        symbol = '₹' if d[4] == 'INR' else '$'
        text += f"ID: {d[0]}\n"
        text += f"User: @{d[2]}\n"
        text += f"Amount: {symbol}{d[3]/100:.2f}\n"
        text += f"Method: {d[5]}\n"
        text += f"Time: {d[9]}\n"
        text += f"To approve: /approve_deposit {d[0]} [amount]\n"
        text += f"To reject: /reject_deposit {d[0]}\n\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="admin_panel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup)

async def admin_withdrawals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await query.edit_message_text("❌ Unauthorized!")
        return
    
    withdrawals = get_pending_withdrawals()
    if not withdrawals:
        await query.edit_message_text("📤 No pending withdrawals.")
        return
    
    text = "📤 PENDING WITHDRAWALS\n\n"
    for w in withdrawals:
        symbol = '₹' if w[4] == 'INR' else '$'
        text += f"ID: {w[0]}\n"
        text += f"User: @{w[2]}\n"
        text += f"Amount: {symbol}{w[3]/100:.2f}\n"
        text += f"Method: {w[5]}\n"
        text += f"UPI: {w[6] or 'N/A'}\n"
        text += f"Address: {w[9] or 'N/A'}\n"
        text += f"Network: {w[10] or 'N/A'}\n"
        text += f"Time: {w[14]}\n"
        text += f"To approve: /approve_withdraw {w[0]}\n"
        text += f"To complete: /complete_withdraw {w[0]}\n"
        text += f"To reject: /reject_withdraw {w[0]}\n\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="admin_panel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup)

async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await query.edit_message_text("❌ Unauthorized!")
        return
    
    users = get_all_users()
    
    if not users:
        await query.edit_message_text("📊 No users found.")
        return
    
    text = "📊 ALL USERS\n\n"
    count = 0
    for u in users:
        if count >= 20:
            break
        symbol = '₹' if u[3] == 'INR' else '$'
        balance = u[4] if u[3] == 'INR' else u[5]
        text += f"👤 @{u[1] or u[2]}\n"
        text += f"🆔 {u[0]}\n"
        text += f"💰 {symbol}{balance/100:.2f}\n"
        text += f"🌐 {u[3]}\n"
        text += "-" * 20 + "\n"
        count += 1
    
    if len(users) > 20:
        text += f"\n... and {len(users) - 20} more users"
    
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="admin_panel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup)

async def admin_add_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await query.edit_message_text("❌ Unauthorized!")
        return
    
    await query.edit_message_text(
        f"""
💰 **ADD BALANCE**

Usage: `/addbalance @username amount`
Example: `/addbalance @john 100`

Amount is in user's currency (INR or USD)

📌 **Limits:**
🇮🇳 INR: ₹{INR_MIN_DEPOSIT/100:.2f} - ₹{INR_MAX_DEPOSIT/100:.2f}
🇺🇸 USD: ${USD_MIN_DEPOSIT/100:.2f} - ${USD_MAX_DEPOSIT/100:.2f}

INR: Use whole numbers (e.g., 100)
USD: Use decimals (e.g., 5.5, 10.25)

Admin: {ADMIN_USERNAME}
        """
    )

async def admin_addbalance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Unauthorized!")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /addbalance @username amount\nExample: /addbalance @john 100")
        return
    
    username = context.args[0].replace('@', '')
    try:
        amount_input = float(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Invalid amount! Please enter a valid number.")
        return
    
    conn = get_db()
    c = conn.cursor()
    
    if username.isdigit():
        c.execute('SELECT user_id, currency, first_name FROM users WHERE user_id = ?', (int(username),))
    else:
        c.execute('SELECT user_id, currency, first_name FROM users WHERE username = ?', (username,))
    
    user = c.fetchone()
    if not user:
        await update.message.reply_text(f"❌ User @{username} not found!")
        conn.close()
        return
    
    target_id = user[0]
    currency = user[1]
    first_name = user[2]
    symbol = '₹' if currency == 'INR' else '$'
    
    if currency == 'USD':
        amount = int(amount_input * 100)
    else:
        amount = int(amount_input * 100)
    
    if currency == 'INR':
        if amount < INR_MIN_DEPOSIT:
            await update.message.reply_text(f"❌ Minimum add balance is ₹{INR_MIN_DEPOSIT/100:.2f}")
            conn.close()
            return
        if amount > INR_MAX_DEPOSIT:
            await update.message.reply_text(f"❌ Maximum add balance is ₹{INR_MAX_DEPOSIT/100:.2f}")
            conn.close()
            return
    else:
        if amount < USD_MIN_DEPOSIT:
            await update.message.reply_text(f"❌ Minimum add balance is ${USD_MIN_DEPOSIT/100:.2f}")
            conn.close()
            return
        if amount > USD_MAX_DEPOSIT:
            await update.message.reply_text(f"❌ Maximum add balance is ${USD_MAX_DEPOSIT/100:.2f}")
            conn.close()
            return
    
    update_wallet(target_id, amount, currency)
    
    balance = get_user_balance(target_id, currency)
    add_transaction(target_id, 'deposit', amount, currency, balance, f"Admin added {symbol}{amount_input:.2f}")
    
    conn.commit()
    conn.close()
    
    await update.message.reply_text(f"✅ Added {symbol}{amount_input:.2f} to @{username}!")
    
    await context.bot.send_message(
        chat_id=target_id,
        text=f"✅ {symbol}{amount_input:.2f} added to your wallet by admin {ADMIN_USERNAME}!"
    )

async def admin_give_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await query.edit_message_text("❌ Unauthorized!")
        return
    
    await query.edit_message_text("⏳ Adding ₹10 to all users...")
    
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT user_id, currency FROM users')
        users = c.fetchall()
        
        count = 0
        for user in users:
            if user[1] == 'INR':
                update_wallet(user[0], 1000, 'INR')
            else:
                update_wallet(user[0], 1000, 'USD')
            count += 1
        
        conn.close()
        await query.edit_message_text(f"✅ Added ₹10 equivalent to {count} users!")
    except Exception as e:
        await query.edit_message_text(f"❌ Error: {str(e)}")

# ============ ADMIN COMMANDS ============

async def admin_approve_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Unauthorized!")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /approve_deposit [deposit_id] [amount]\n\nExample: /approve_deposit 5 100")
        return
    
    try:
        deposit_id = int(context.args[0])
        amount_input = float(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Invalid input! Please enter valid numbers.\nExample: /approve_deposit 5 100")
        return
    
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('UPDATE deposit_requests SET amount = ? WHERE id = ?', (int(amount_input * 100), deposit_id))
        conn.commit()
        conn.close()
        
        success, deposit = approve_deposit(deposit_id)
        
        if success and deposit:
            symbol = '₹' if deposit[4] == 'INR' else '$'
            await update.message.reply_text(
                f"✅ **Deposit #{deposit_id} approved!**\n\n"
                f"User: @{deposit[2]}\n"
                f"Amount: {symbol}{amount_input:.2f}\n"
                f"Currency: {deposit[4]}\n\n"
                f"✅ Balance added to user's wallet!"
            )
            
            try:
                await context.bot.send_message(
                    chat_id=deposit[1],
                    text=f"""
✅ **Your deposit has been approved!**

💰 Amount: {symbol}{amount_input:.2f}
💱 Currency: {deposit[4]}

Your balance has been updated! 🎉

Thank you for using Casino India!
                    """
                )
            except Exception as e:
                logger.error(f"Could not notify user: {e}")
        else:
            await update.message.reply_text("❌ Failed to approve deposit!\n\nPlease check if the deposit is still pending.")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def admin_reject_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Unauthorized!")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /reject_deposit [deposit_id] [reason]\n\nExample: /reject_deposit 5 Invalid screenshot")
        return
    
    try:
        deposit_id = int(context.args[0])
        reason = " ".join(context.args[1:]) if len(context.args) > 1 else "No reason provided"
    except ValueError:
        await update.message.reply_text("❌ Invalid input! Please enter a valid deposit ID.")
        return
    
    try:
        success, deposit = reject_deposit(deposit_id, reason)
        
        if success and deposit:
            symbol = '₹' if deposit[4] == 'INR' else '$'
            await update.message.reply_text(
                f"✅ **Deposit #{deposit_id} rejected!**\n\n"
                f"User: @{deposit[2]}\n"
                f"Amount: {symbol}{deposit[3]/100:.2f}\n"
                f"Reason: {reason}"
            )
            
            try:
                await context.bot.send_message(
                    chat_id=deposit[1],
                    text=f"""
❌ **Your deposit has been rejected!**

💰 Amount: {symbol}{deposit[3]/100:.2f}
📌 Reason: {reason}

Please try again with valid payment proof.

Contact admin for more details.
                    """
                )
            except Exception as e:
                logger.error(f"Could not notify user: {e}")
        else:
            await update.message.reply_text("❌ Failed to reject deposit!\n\nPlease check if the deposit is still pending.")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

# ============ WITHDRAWAL ADMIN COMMANDS ============

async def admin_approve_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Approve a withdrawal request"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Unauthorized!")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /approve_withdraw [withdraw_id]\n\nExample: /approve_withdraw 5")
        return
    
    try:
        withdraw_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid input! Please enter a valid withdraw ID.")
        return
    
    try:
        success, withdraw = approve_withdrawal(withdraw_id)
        
        if success and withdraw:
            symbol = '₹' if withdraw[4] == 'INR' else '$'
            await update.message.reply_text(
                f"✅ **Withdraw #{withdraw_id} approved!**\n\n"
                f"User: @{withdraw[2]}\n"
                f"Amount: {symbol}{withdraw[3]/100:.2f}\n"
                f"Currency: {withdraw[4]}\n"
                f"Method: {withdraw[5]}\n\n"
                f"📌 Use /complete_withdraw {withdraw_id} to complete the transfer."
            )
            
            try:
                await context.bot.send_message(
                    chat_id=withdraw[1],
                    text=f"""
✅ **Your withdrawal has been approved!**

💰 Amount: {symbol}{withdraw[3]/100:.2f}
💱 Currency: {withdraw[4]}

Admin will process your withdrawal soon. 🎉
                    """
                )
            except Exception as e:
                logger.error(f"Could not notify user: {e}")
        else:
            await update.message.reply_text("❌ Failed to approve withdrawal!\n\nPlease check if the withdrawal is still pending.")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def admin_complete_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Complete a withdrawal (mark as sent) and send payment confirmation image"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Unauthorized! Only admin can use this command.")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text(
            "❌ **Usage:** `/complete_withdraw [withdraw_id]`\n\n"
            "Example: `/complete_withdraw 5`\n\n"
            "📌 To find the withdraw ID, use:\n"
            "• `/admin_panel` → Pending Withdrawals\n"
            "• Or check the withdrawal notification"
        )
        return
    
    try:
        withdraw_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid withdraw ID! Please enter a valid number.\nExample: `/complete_withdraw 5`")
        return
    
    logger.info(f"Admin {user_id} attempting to complete withdrawal #{withdraw_id}")
    await update.message.reply_text(f"⏳ Processing withdrawal #{withdraw_id}...")
    
    try:
        # Check if the withdrawal exists
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT * FROM withdraw_requests WHERE id = ?', (withdraw_id,))
        withdraw = c.fetchone()
        conn.close()
        
        if not withdraw:
            await update.message.reply_text(f"❌ Withdrawal #{withdraw_id} not found!\n\nPlease check the ID and try again.")
            return
        
        if withdraw[12] == 'completed':
            await update.message.reply_text(f"⚠️ Withdrawal #{withdraw_id} is already completed!")
            return
        
        if withdraw[12] != 'approved':
            await update.message.reply_text(
                f"⚠️ Withdrawal #{withdraw_id} is not approved yet!\n"
                f"Current status: {withdraw[12].upper()}\n\n"
                f"Please use `/approve_withdraw {withdraw_id}` first."
            )
            return
        
        # Complete the withdrawal
        success, completed_withdraw = complete_withdrawal(withdraw_id)
        
        if success and completed_withdraw:
            symbol = '₹' if completed_withdraw[4] == 'INR' else '$'
            amount_display = completed_withdraw[3] / 100
            user_id_target = completed_withdraw[1]
            username = completed_withdraw[2] or f"User{user_id_target}"
            
            balance = get_user_balance(user_id_target, completed_withdraw[4]) / 100
            
            await update.message.reply_text(
                f"✅ **Withdrawal #{withdraw_id} completed successfully!**\n\n"
                f"👤 User: @{username}\n"
                f"🆔 ID: {user_id_target}\n"
                f"💰 Amount: {symbol}{amount_display:.2f}\n"
                f"💱 Currency: {completed_withdraw[4]}\n"
                f"💳 Method: {completed_withdraw[5]}\n\n"
                f"📊 Updated Balance: {symbol}{balance:.2f}\n"
                f"✅ Transaction recorded in user's history!"
            )
            
            # ============ SEND PAYMENT SUCCESS IMAGE TO USER ============
            try:
                # Check if payment success image exists
                if os.path.exists(PAYMENT_SUCCESS_IMAGE):
                    with open(PAYMENT_SUCCESS_IMAGE, 'rb') as photo:
                        await context.bot.send_photo(
                            chat_id=user_id_target,
                            photo=photo,
                            caption=f"""
🎉 **THANK YOU!**

Your withdrawal of **{symbol}{amount_display:.2f}** has been 
**SUCCESSFULLY COMPLETED!**

💳 Method: {completed_withdraw[5]}
📅 Date: {datetime.now().strftime('%d %b %Y, %I:%M %p')}

Welcome to our CASINO GROUP! 🎰

💡 Current Balance: {symbol}{balance:.2f}

_Thank you for choosing Casino India!_
                            """
                        )
                        logger.info(f"Payment success image sent to user {user_id_target}")
                else:
                    # If image doesn't exist, send text message
                    await context.bot.send_message(
                        chat_id=user_id_target,
                        text=f"""
🎉 **THANK YOU!**

Your withdrawal of **{symbol}{amount_display:.2f}** has been 
**SUCCESSFULLY COMPLETED!**

💳 Method: {completed_withdraw[5]}
📅 Date: {datetime.now().strftime('%d %b %Y, %I:%M %p')}

Welcome to our CASINO GROUP! 🎰

💡 Current Balance: {symbol}{balance:.2f}

_Thank you for choosing Casino India!_
                        """
                    )
                    logger.warning(f"Payment success image not found at {PAYMENT_SUCCESS_IMAGE}")
            except Exception as e:
                logger.error(f"Could not send payment success image to user {user_id_target}: {e}")
                # Fallback: send text message
                try:
                    await context.bot.send_message(
                        chat_id=user_id_target,
                        text=f"""
🎉 **THANK YOU!**

Your withdrawal of **{symbol}{amount_display:.2f}** has been 
**SUCCESSFULLY COMPLETED!**

💳 Method: {completed_withdraw[5]}
📅 Date: {datetime.now().strftime('%d %b %Y, %I:%M %p')}

Welcome to our CASINO GROUP! 🎰

💡 Current Balance: {symbol}{balance:.2f}

_Thank you for choosing Casino India!_
                        """
                    )
                except Exception as e2:
                    logger.error(f"Could not send fallback message: {e2}")
        else:
            await update.message.reply_text(
                f"❌ Failed to complete withdrawal #{withdraw_id}!\n\n"
                f"Please check if the withdrawal exists and is approved.\n"
                f"Try: `/admin_withdrawals` to see all pending withdrawals."
            )
            
    except sqlite3.OperationalError as e:
        if "database is locked" in str(e):
            await update.message.reply_text("⏳ Database is busy, please try again in a few seconds.")
        else:
            logger.error(f"Database error in complete_withdraw: {e}")
            await update.message.reply_text(f"❌ Database error: {str(e)}")
    except Exception as e:
        logger.error(f"Error in complete_withdraw: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def admin_reject_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reject a withdrawal request"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Unauthorized!")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /reject_withdraw [withdraw_id] [reason]\n\nExample: /reject_withdraw 5 Invalid UPI ID")
        return
    
    try:
        withdraw_id = int(context.args[0])
        reason = " ".join(context.args[1:]) if len(context.args) > 1 else "No reason provided"
    except ValueError:
        await update.message.reply_text("❌ Invalid input! Please enter a valid withdraw ID.")
        return
    
    try:
        success, withdraw = reject_withdrawal(withdraw_id, reason)
        
        if success and withdraw:
            symbol = '₹' if withdraw[4] == 'INR' else '$'
            await update.message.reply_text(
                f"✅ **Withdraw #{withdraw_id} rejected!**\n\n"
                f"User: @{withdraw[2]}\n"
                f"Amount: {symbol}{withdraw[3]/100:.2f}\n"
                f"Reason: {reason}\n\n"
                f"✅ Funds refunded to user's wallet!"
            )
            
            try:
                await context.bot.send_message(
                    chat_id=withdraw[1],
                    text=f"""
❌ **Your withdrawal has been rejected!**

💰 Amount: {symbol}{withdraw[3]/100:.2f}
📌 Reason: {reason}

Funds have been refunded to your wallet.

Please try again with correct details.
                    """
                )
            except Exception as e:
                logger.error(f"Could not notify user: {e}")
        else:
            await update.message.reply_text("❌ Failed to reject withdrawal!\n\nPlease check if the withdrawal is still pending.")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

# ============ MAIN ============

def main():
    if not os.path.exists(DB_PATH):
        init_db()
    else:
        init_db()
    
    request = HTTPXRequest(
        connection_pool_size=8,
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=30.0,
        http_version="1.1"
    )
    
    app = ApplicationBuilder().token(BOT_TOKEN).request(request).build()
    
    # User commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("withdraw", withdraw_command))
    app.add_handler(CommandHandler("withdraw_usdt", withdraw_usdt_command))
    
    # Admin commands
    app.add_handler(CommandHandler("addbalance", admin_addbalance))
    app.add_handler(CommandHandler("approve_deposit", admin_approve_deposit))
    app.add_handler(CommandHandler("reject_deposit", admin_reject_deposit))
    app.add_handler(CommandHandler("approve_withdraw", admin_approve_withdraw))
    app.add_handler(CommandHandler("complete_withdraw", admin_complete_withdraw))
    app.add_handler(CommandHandler("reject_withdraw", admin_reject_withdraw))
    
    # Callback handlers - User
    app.add_handler(CallbackQueryHandler(payment_menu, pattern="^payment_menu$"))
    app.add_handler(CallbackQueryHandler(set_currency, pattern="^currency_"))
    app.add_handler(CallbackQueryHandler(deposit_main, pattern="^deposit_main$"))
    app.add_handler(CallbackQueryHandler(deposit_inr_upi, pattern="^deposit_inr_upi$"))
    app.add_handler(CallbackQueryHandler(deposit_inr_bank, pattern="^deposit_inr_bank$"))
    app.add_handler(CallbackQueryHandler(deposit_usdt, pattern="^deposit_usdt$"))
    app.add_handler(CallbackQueryHandler(deposit_confirm, pattern="^deposit_confirm$"))
    app.add_handler(CallbackQueryHandler(withdraw_main, pattern="^withdraw_main$"))
    app.add_handler(CallbackQueryHandler(withdraw_upi, pattern="^withdraw_upi$"))
    app.add_handler(CallbackQueryHandler(withdraw_usdt, pattern="^withdraw_usdt$"))
    app.add_handler(CallbackQueryHandler(deposit_history, pattern="^deposit_history$"))
    app.add_handler(CallbackQueryHandler(withdraw_history, pattern="^withdraw_history$"))
    app.add_handler(CallbackQueryHandler(transactions, pattern="^transactions$"))
    app.add_handler(CallbackQueryHandler(change_currency, pattern="^change_currency$"))
    
    # Callback handlers - Admin
    app.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
    app.add_handler(CallbackQueryHandler(admin_deposits, pattern="^admin_deposits$"))
    app.add_handler(CallbackQueryHandler(admin_withdrawals, pattern="^admin_withdrawals$"))
    app.add_handler(CallbackQueryHandler(admin_users, pattern="^admin_users$"))
    app.add_handler(CallbackQueryHandler(admin_add_balance, pattern="^admin_add_balance$"))
    app.add_handler(CallbackQueryHandler(admin_give_all, pattern="^admin_give_all$"))
    app.add_handler(CallbackQueryHandler(admin_approve_button, pattern="^admin_approve_"))
    app.add_handler(CallbackQueryHandler(admin_reject_button, pattern="^admin_reject_"))
    
    # Message handlers for screenshots
    app.add_handler(MessageHandler(filters.PHOTO, handle_screenshot))
    
    print("💳 Payment Bot is starting...")
    print(f"👑 Admin: {ADMIN_USERNAME}")
    print(f"💳 UPI: {ADMIN_UPI_ID}")
    print(f"🪙 USDT Address: {USD_PAYMENT['crypto']['address']}")
    print("✅ Payment Bot is running!")
    print("📌 INR: UPI & Bank Deposit, UPI Withdraw")
    print(f"📌 INR Limits: ₹{INR_MIN_DEPOSIT/100:.2f} - ₹{INR_MAX_DEPOSIT/100:.2f}")
    print("📌 USD: USDT (BEP20) Deposit & Withdraw (supports decimals like 5.5)")
    print(f"📌 USD Limits: ${USD_MIN_DEPOSIT/100:.2f} - ${USD_MAX_DEPOSIT/100:.2f}")
    print("=" * 40)
    print("📸 Payment Success Image Path:", PAYMENT_SUCCESS_IMAGE)
    if os.path.exists(PAYMENT_SUCCESS_IMAGE):
        print("✅ Payment success image found!")
    else:
        print("❌ Payment success image NOT found! Please save it as:", PAYMENT_SUCCESS_IMAGE)
    print("=" * 40)
    app.run_polling()

if __name__ == '__main__':
    main()