import logging
from typing import Dict, Optional, List
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)
from telegram.request import HTTPXRequest
from datetime import datetime, timedelta
import sqlite3
import random
import string
import asyncio
import os
import json
import time
from functools import wraps

# ============ CONFIGURATION ============

BOT_TOKEN = "8819667974:AAFfXGJ3Pnb8Bh9HqV7gtO3vRM5Jd6cr1yM"
BOT_USERNAME = "CasinoPayment26_bot"

# Brand Name
BRAND_NAME = "🎰 CASINO INDIA"
BRAND_EMOJI = "🎰"

# Admin
ADMIN_USER_ID = 5943318266
ADMIN_USERNAME = "@XTOP_879"

# Payment Bot Link
PAYMENT_BOT_LINK = "https://t.me/CasinoIndia2026_bot"

# IMPORTANT: Use the SAME database as payment bot
DB_PATH = "payment_bot.db"  # Shared database

# Game Settings
WINNER_GETS_PERCENT = 85  # Winner gets 85%
PLATFORM_FEE_PERCENT = 15  # Platform fee 15% (Hidden from users)

# PVP Bet Amounts
INR_BET_AMOUNTS = [10, 20, 30, 40, 50, 100, 200]
USD_BET_AMOUNTS = [1, 2, 3, 4, 10]

# PVP Rounds Options
ROUNDS_OPTIONS = [
    {"key": "2r1w", "label": "2 Rolls 1 Win", "rolls": 2},
    {"key": "3r1w", "label": "3 Rolls 1 Win", "rolls": 3},
    {"key": "4r1w", "label": "4 Rolls 1 Win", "rolls": 4},
    {"key": "5r1w", "label": "5 Rolls 1 Win", "rolls": 5},
]

# Dice emojis
DICE_EMOJIS = {
    1: "⚀",
    2: "⚁", 
    3: "⚂",
    4: "⚃",
    5: "⚄",
    6: "⚅"
}

# Challenge timeout (seconds)
CHALLENGE_TIMEOUT = 120  # 2 minutes

# NEW LEVEL SYSTEM (XP based)
LEVELS = [
    {"level": 1, "name": "Bronze", "min_xp": 0, "max_xp": 999, "badge": "🥉"},
    {"level": 2, "name": "Silver", "min_xp": 1000, "max_xp": 2999, "badge": "🥈"},
    {"level": 3, "name": "Gold", "min_xp": 3000, "max_xp": 6999, "badge": "🥇"},
    {"level": 4, "name": "Platinum", "min_xp": 7000, "max_xp": 14999, "badge": "💎"},
    {"level": 5, "name": "Diamond", "min_xp": 15000, "max_xp": 29999, "badge": "💠"},
    {"level": 6, "name": "Master", "min_xp": 30000, "max_xp": 59999, "badge": "👑"},
    {"level": 7, "name": "Elite", "min_xp": 60000, "max_xp": 99999, "badge": "🔥"},
    {"level": 8, "name": "Legend", "min_xp": 100000, "max_xp": 199999, "badge": "⚡"},
    {"level": 9, "name": "Champion", "min_xp": 200000, "max_xp": 499999, "badge": "🏆"},
    {"level": 10, "name": "Royal", "min_xp": 500000, "max_xp": 999999, "badge": "🌟"},
    {"level": 11, "name": "Grandmaster", "min_xp": 1000000, "max_xp": 2999999, "badge": "👑"},
    {"level": 12, "name": "Immortal", "min_xp": 3000000, "max_xp": float('inf'), "badge": "💠"},
]

# ============ DECORATOR FOR PRIVATE CHAT ONLY ============

def private_only(func):
    """Decorator to restrict command/callback to private chats only"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if update.callback_query:
            chat = update.callback_query.message.chat
        else:
            chat = update.effective_chat
        
        if chat.type != "private":
            if update.callback_query:
                await update.callback_query.answer("❌ Please use this bot in a private chat.", show_alert=True)
                await update.callback_query.edit_message_text("❌ This bot only works in private chats for security reasons.\n\nPlease start the bot in a private chat: @CasinoPayment26_bot")
            else:
                await update.message.reply_text("❌ Please use this bot in a private chat for security reasons.\n\nStart the bot here: @CasinoPayment26_bot")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

# ============ HELPER FUNCTIONS ============

def get_brand_header():
    return """
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃  🎰 CASINO INDIA  🎰              ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
"""

def format_currency(amount, currency='INR'):
    symbol = '₹' if currency == 'INR' else '$'
    return f"{symbol}{amount/100:.2f}"

def get_dice_display(rolls):
    if not rolls:
        return ""
    return ' '.join([f"{DICE_EMOJIS.get(r, '🎲')}" for r in rolls])

def get_level_info(xp):
    """Get level info based on XP"""
    for level in reversed(LEVELS):
        if xp >= level["min_xp"]:
            return level
    return LEVELS[0]

def get_level_progress(xp):
    """Get progress to next level as percentage"""
    current = get_level_info(xp)
    next_level = None
    
    for i, level in enumerate(LEVELS):
        if level["level"] == current["level"] and i < len(LEVELS) - 1:
            next_level = LEVELS[i + 1]
            break
    
    if not next_level:
        return 100  # Max level
    
    xp_in_level = xp - current["min_xp"]
    xp_needed = next_level["min_xp"] - current["min_xp"]
    
    if xp_needed <= 0:
        return 100
    
    return min(100, int((xp_in_level / xp_needed) * 100))

def safe_int(value):
    try:
        return int(value) if value is not None else 0
    except (ValueError, TypeError):
        return 0

def safe_str(value):
    return str(value) if value is not None else ""

# ============ ENHANCED DATABASE ============

def get_db():
    """Get database connection with timeout and retry"""
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn

def init_db_enhanced():
    """Initialize enhanced database tables"""
    conn = get_db()
    c = conn.cursor()
    
    # Existing users table columns
    c.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in c.fetchall()]
    
    # Base users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            currency TEXT DEFAULT 'INR',
            coins INTEGER DEFAULT 0,
            wallet_balance_inr INTEGER DEFAULT 0,
            wallet_balance_usd INTEGER DEFAULT 0,
            total_games INTEGER DEFAULT 0,
            total_wins INTEGER DEFAULT 0,
            total_losses INTEGER DEFAULT 0,
            total_draws INTEGER DEFAULT 0,
            win_streak INTEGER DEFAULT 0,
            max_win_streak INTEGER DEFAULT 0,
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
            total_lost_inr INTEGER DEFAULT 0,
            total_lost_usd INTEGER DEFAULT 0,
            total_wagered_inr INTEGER DEFAULT 0,
            total_wagered_usd INTEGER DEFAULT 0,
            activity_points INTEGER DEFAULT 0,
            daily_activity INTEGER DEFAULT 0,
            weekly_activity INTEGER DEFAULT 0,
            monthly_activity INTEGER DEFAULT 0,
            last_activity_date TIMESTAMP,
            badges TEXT DEFAULT "[]",
            referred_by INTEGER,
            referral_count INTEGER DEFAULT 0,
            total_referral_bonus INTEGER DEFAULT 0,
            favorite_game TEXT DEFAULT "None",
            biggest_win INTEGER DEFAULT 0,
            biggest_win_currency TEXT DEFAULT "INR",
            last_game_played TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Add new columns if they don't exist
    new_columns = {
        'coins': 'INTEGER DEFAULT 0',
        'total_wagered_inr': 'INTEGER DEFAULT 0',
        'total_wagered_usd': 'INTEGER DEFAULT 0',
        'activity_points': 'INTEGER DEFAULT 0',
        'daily_activity': 'INTEGER DEFAULT 0',
        'weekly_activity': 'INTEGER DEFAULT 0',
        'monthly_activity': 'INTEGER DEFAULT 0',
        'last_activity_date': 'TIMESTAMP',
        'badges': 'TEXT DEFAULT "[]"',
        'referred_by': 'INTEGER',
        'referral_count': 'INTEGER DEFAULT 0',
        'total_referral_bonus': 'INTEGER DEFAULT 0',
        'favorite_game': 'TEXT DEFAULT "None"',
        'biggest_win': 'INTEGER DEFAULT 0',
        'biggest_win_currency': 'TEXT DEFAULT "INR"',
        'last_game_played': 'TIMESTAMP'
    }
    
    for col, dtype in new_columns.items():
        if col not in columns:
            try:
                c.execute(f'ALTER TABLE users ADD COLUMN {col} {dtype}')
                print(f"✅ Added column: {col}")
            except sqlite3.OperationalError as e:
                print(f"⚠️ Could not add column {col}: {e}")
    
    # Create game_history table
    c.execute('''
        CREATE TABLE IF NOT EXISTS game_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id TEXT,
            game_type TEXT,
            mode TEXT,
            rounds_type TEXT,
            player1_id INTEGER,
            player2_id INTEGER,
            winner_id INTEGER,
            bet_amount INTEGER,
            currency TEXT,
            platform_fee INTEGER,
            commission_fee INTEGER,
            winner_amount INTEGER,
            player1_rolls TEXT,
            player2_rolls TEXT,
            player1_total INTEGER,
            player2_total INTEGER,
            status TEXT DEFAULT 'completed',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create activity_log table
    c.execute('''
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            activity_type TEXT,
            points INTEGER DEFAULT 0,
            currency TEXT DEFAULT 'INR',
            amount INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create wagers table
    c.execute('''
        CREATE TABLE IF NOT EXISTS wagers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            game_type TEXT,
            bet_amount INTEGER,
            currency TEXT,
            won BOOLEAN DEFAULT 0,
            win_amount INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create referrals table
    c.execute('''
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER,
            referred_id INTEGER,
            bonus_amount INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create transactions table if not exists
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
    print("✅ Enhanced database initialized!")

# ============ USER FUNCTIONS ============

def get_or_create_user(user_id, username, first_name, last_name=None):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = c.fetchone()
    
    if not user:
        referral_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        username = username if username else f"user_{user_id}"
        first_name = first_name if first_name else "User"
        last_name = last_name if last_name else ""
        
        c.execute('''
            INSERT INTO users (user_id, username, first_name, last_name, referral_code, 
                              wallet_balance_inr, wallet_balance_usd, coins)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, username, first_name, last_name, referral_code, 0, 0, 0))
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
            'user_id': safe_int(user[0]),
            'username': safe_str(user[1] or f"User{user[0]}"),
            'first_name': safe_str(user[2] or "User"),
            'last_name': safe_str(user[3] or ""),
            'currency': safe_str(user[4] if len(user) > 4 else 'INR'),
            'coins': safe_int(user[5] if len(user) > 5 else 0),
            'wallet_balance_inr': safe_int(user[6] if len(user) > 6 else 0),
            'wallet_balance_usd': safe_int(user[7] if len(user) > 7 else 0),
            'total_games': safe_int(user[8] if len(user) > 8 else 0),
            'total_wins': safe_int(user[9] if len(user) > 9 else 0),
            'total_losses': safe_int(user[10] if len(user) > 10 else 0),
            'total_draws': safe_int(user[11] if len(user) > 11 else 0),
            'win_streak': safe_int(user[12] if len(user) > 12 else 0),
            'max_win_streak': safe_int(user[13] if len(user) > 13 else 0),
            'rating': safe_int(user[14] if len(user) > 14 else 0),
            'level': safe_int(user[15] if len(user) > 15 else 1),
            'experience': safe_int(user[16] if len(user) > 16 else 0),
            'referral_code': safe_str(user[17] if len(user) > 17 else ''),
            'daily_bonus_claimed': safe_str(user[18] if len(user) > 18 else None),
            'daily_bonus_streak': safe_int(user[19] if len(user) > 19 else 0),
            'total_deposited_inr': safe_int(user[20] if len(user) > 20 else 0),
            'total_deposited_usd': safe_int(user[21] if len(user) > 21 else 0),
            'total_withdrawn_inr': safe_int(user[22] if len(user) > 22 else 0),
            'total_withdrawn_usd': safe_int(user[23] if len(user) > 23 else 0),
            'total_won_inr': safe_int(user[24] if len(user) > 24 else 0),
            'total_won_usd': safe_int(user[25] if len(user) > 25 else 0),
            'total_lost_inr': safe_int(user[26] if len(user) > 26 else 0),
            'total_lost_usd': safe_int(user[27] if len(user) > 27 else 0),
            'created_at': safe_str(user[28] if len(user) > 28 else None),
            'total_wagered_inr': safe_int(user[29] if len(user) > 29 else 0),
            'total_wagered_usd': safe_int(user[30] if len(user) > 30 else 0),
            'activity_points': safe_int(user[31] if len(user) > 31 else 0),
            'daily_activity': safe_int(user[32] if len(user) > 32 else 0),
            'weekly_activity': safe_int(user[33] if len(user) > 33 else 0),
            'monthly_activity': safe_int(user[34] if len(user) > 34 else 0),
            'last_activity_date': safe_str(user[35] if len(user) > 35 else None),
            'badges': json.loads(user[36]) if len(user) > 36 and user[36] else [],
            'referred_by': safe_int(user[37] if len(user) > 37 else None),
            'referral_count': safe_int(user[38] if len(user) > 38 else 0),
            'total_referral_bonus': safe_int(user[39] if len(user) > 39 else 0),
            'favorite_game': safe_str(user[40] if len(user) > 40 else 'None'),
            'biggest_win': safe_int(user[41] if len(user) > 41 else 0),
            'biggest_win_currency': safe_str(user[42] if len(user) > 42 else 'INR'),
            'last_game_played': safe_str(user[43] if len(user) > 43 else None)
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

def update_wallet(user_id, amount, currency='INR'):
    conn = get_db()
    c = conn.cursor()
    if currency == 'INR':
        c.execute('UPDATE users SET wallet_balance_inr = wallet_balance_inr + ? WHERE user_id = ?', (amount, user_id))
    else:
        c.execute('UPDATE users SET wallet_balance_usd = wallet_balance_usd + ? WHERE user_id = ?', (amount, user_id))
    conn.commit()
    conn.close()

def add_transaction(user_id, type, amount, currency, balance_after, description):
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        INSERT INTO transactions (user_id, type, amount, currency, balance_after, description)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, type, amount, currency, balance_after, description))
    conn.commit()
    conn.close()

def update_user_stats(user_id, won=None, draw=False, bet_amount=0, currency='INR', game_type='dice'):
    """Update user statistics with proper locking"""
    conn = get_db()
    c = conn.cursor()
    
    try:
        # First, get current user data
        c.execute('''SELECT total_games, total_wins, total_losses, total_draws, win_streak, max_win_streak, 
                     rating, experience, level, favorite_game, biggest_win, biggest_win_currency, 
                     total_wagered_inr, total_wagered_usd, total_won_inr, total_won_usd, total_lost_inr, total_lost_usd,
                     wallet_balance_inr, wallet_balance_usd
                     FROM users WHERE user_id = ?''', (user_id,))
        user = c.fetchone()
        
        if not user:
            conn.close()
            return False
        
        (total_games, total_wins, total_losses, total_draws, win_streak, max_win_streak,
         rating, experience, level, favorite_game, biggest_win, biggest_win_currency,
         total_wagered_inr, total_wagered_usd, total_won_inr, total_won_usd, total_lost_inr, total_lost_usd,
         wallet_balance_inr, wallet_balance_usd) = user
        
        # Increment total games
        total_games += 1
        
        # Calculate total bet amount for this game
        total_pot = bet_amount * 2
        
        # Update wagered totals
        if currency == 'INR':
            total_wagered_inr += total_pot
        else:
            total_wagered_usd += total_pot
        
        # Update favorite game
        if favorite_game == 'None' or favorite_game is None:
            favorite_game = game_type
        
        xp_gained = 0
        # Update stats based on result
        if draw:
            total_draws += 1
            win_streak = 0
            xp_gained = 5
        elif won is True:
            total_wins += 1
            win_streak += 1
            if win_streak > max_win_streak:
                max_win_streak = win_streak
            rating += 10
            xp_gained = 25
            
            # Track biggest win (winner gets 85% of pot)
            win_amount = total_pot * WINNER_GETS_PERCENT // 100
            if win_amount > biggest_win:
                biggest_win = win_amount
                biggest_win_currency = currency
            
            # Update total won
            if currency == 'INR':
                total_won_inr += win_amount
            else:
                total_won_usd += win_amount
                
        elif won is False:
            total_losses += 1
            win_streak = 0
            rating -= 5
            xp_gained = 5
            
            # Update total lost (the player loses their bet)
            if currency == 'INR':
                total_lost_inr += bet_amount
            else:
                total_lost_usd += bet_amount
        
        # Ensure rating doesn't go below 0
        if rating < 0:
            rating = 0
        
        # Update experience
        experience += xp_gained
        
        # Update level based on XP
        new_level = 1
        for lvl in LEVELS:
            if experience >= lvl["min_xp"]:
                new_level = lvl["level"]
        level = new_level
        
        # Update all user stats
        c.execute('''
            UPDATE users SET 
                total_games = ?,
                total_wins = ?,
                total_losses = ?,
                total_draws = ?,
                win_streak = ?,
                max_win_streak = ?,
                rating = ?,
                experience = ?,
                level = ?,
                favorite_game = ?,
                biggest_win = ?,
                biggest_win_currency = ?,
                total_wagered_inr = ?,
                total_wagered_usd = ?,
                total_won_inr = ?,
                total_won_usd = ?,
                total_lost_inr = ?,
                total_lost_usd = ?,
                last_game_played = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (
            total_games,
            total_wins,
            total_losses,
            total_draws,
            win_streak,
            max_win_streak,
            rating,
            experience,
            level,
            favorite_game,
            biggest_win,
            biggest_win_currency,
            total_wagered_inr,
            total_wagered_usd,
            total_won_inr,
            total_won_usd,
            total_lost_inr,
            total_lost_usd,
            user_id
        ))
        
        conn.commit()
        logging.info(f"Updated stats for user {user_id}: Games={total_games}, Wins={total_wins}, Level={level}, XP={experience}")
        
    except Exception as e:
        logging.error(f"Error updating user stats: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()
    
    # Update activity separately
    try:
        update_user_activity(user_id, 2 if won else 1)
    except Exception as e:
        logging.error(f"Error updating activity: {e}")
    
    return True

def update_user_activity(user_id, points=1):
    """Update user activity points with proper locking"""
    conn = get_db()
    c = conn.cursor()
    
    try:
        current_time = datetime.now()
        current_date = current_time.strftime('%Y-%m-%d')
        
        c.execute('''
            SELECT activity_points, daily_activity, weekly_activity, monthly_activity, last_activity_date
            FROM users WHERE user_id = ?
        ''', (user_id,))
        user = c.fetchone()
        
        if not user:
            conn.close()
            return
        
        activity_points, daily_activity, weekly_activity, monthly_activity, last_date = user
        
        # Reset daily activity if new day
        if last_date and last_date[:10] != current_date:
            daily_activity = 0
        
        # Reset weekly activity if new week
        if last_date:
            try:
                last_week = datetime.strptime(last_date[:10], '%Y-%m-%d').isocalendar()[1]
                current_week = current_time.isocalendar()[1]
                if last_week != current_week:
                    weekly_activity = 0
            except:
                pass
        
        # Reset monthly activity if new month
        if last_date:
            try:
                last_month = datetime.strptime(last_date[:10], '%Y-%m-%d').month
                current_month = current_time.month
                if last_month != current_month:
                    monthly_activity = 0
            except:
                pass
        
        # Update points
        activity_points += points
        daily_activity += points
        weekly_activity += points
        monthly_activity += points
        
        c.execute('''
            UPDATE users SET 
                activity_points = ?,
                daily_activity = ?,
                weekly_activity = ?,
                monthly_activity = ?,
                last_activity_date = ?
            WHERE user_id = ?
        ''', (activity_points, daily_activity, weekly_activity, monthly_activity, current_time, user_id))
        
        conn.commit()
    except sqlite3.OperationalError as e:
        logging.error(f"Database locked in update_user_activity: {e}")
        conn.rollback()
    finally:
        conn.close()
    return daily_activity

def save_game_history(game_data):
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        INSERT INTO game_history 
        (game_id, game_type, mode, rounds_type, player1_id, player2_id, winner_id, 
         bet_amount, currency, platform_fee, commission_fee, winner_amount, 
         player1_rolls, player2_rolls, player1_total, player2_total)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        game_data.get('game_id'),
        game_data.get('game_type', 'dice'),
        'pvp',
        game_data.get('rounds_type'),
        game_data.get('player1_id'),
        game_data.get('player2_id'),
        game_data.get('winner_id'),
        game_data.get('bet_amount', 0),
        game_data.get('currency', 'INR'),
        game_data.get('platform_fee', 0),
        game_data.get('commission_fee', 0),
        game_data.get('winner_amount', 0),
        game_data.get('player1_rolls', '[]'),
        game_data.get('player2_rolls', '[]'),
        game_data.get('player1_total', 0),
        game_data.get('player2_total', 0)
    ))
    conn.commit()
    conn.close()

def get_game_history(user_id, limit=10, offset=0):
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        SELECT * FROM game_history 
        WHERE (player1_id = ? OR player2_id = ?) AND mode = 'pvp'
        ORDER BY created_at DESC LIMIT ? OFFSET ?
    ''', (user_id, user_id, limit, offset))
    games = c.fetchall()
    conn.close()
    return games

def get_total_history_count(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        SELECT COUNT(*) FROM game_history 
        WHERE (player1_id = ? OR player2_id = ?) AND mode = 'pvp'
    ''', (user_id, user_id))
    count = c.fetchone()[0]
    conn.close()
    return safe_int(count)

# ============ DAILY BONUS FUNCTIONS ============

def db_claim_daily_bonus(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT daily_bonus_claimed, daily_bonus_streak FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    
    if not result:
        conn.close()
        return False, "User not found"
    
    streak = safe_int(result[1] or 0)
    
    if result[0]:
        try:
            last_claim = datetime.strptime(result[0], '%Y-%m-%d %H:%M:%S')
            if (datetime.now() - last_claim).days < 1:
                conn.close()
                return False, f"Already claimed today! Streak: {streak} days"
            
            if (datetime.now() - last_claim).days == 1:
                streak += 1
            else:
                streak = 1
        except:
            streak = 1
    else:
        streak = 1
    
    currency = get_user_currency(user_id)
    
    if streak >= 10:
        bonus = 1500
        bonus_msg = "₹15 (10 Days Streak!) 🎉"
    elif streak >= 3:
        bonus = 1000
        bonus_msg = "₹10 (3 Days Streak!) 🎉"
    else:
        bonus = 0
        bonus_msg = f"Need {3 - streak} more days for ₹10"
    
    if bonus > 0:
        if currency == 'USD':
            bonus = int(bonus / 83)
        
        update_wallet(user_id, bonus, currency)
        
        symbol = '₹' if currency == 'INR' else '$'
        bonus_display = f"{symbol}{bonus/100:.2f}"
    else:
        bonus_display = "₹0"
    
    balance = get_user_balance(user_id, currency)
    add_transaction(user_id, 'daily_bonus', bonus, currency, balance, f"Daily bonus - Day {streak}")
    
    c.execute('''
        UPDATE users SET 
            daily_bonus_claimed = CURRENT_TIMESTAMP,
            daily_bonus_streak = ?
        WHERE user_id = ?
    ''', (streak, user_id))
    conn.commit()
    conn.close()
    
    return True, f"Day {streak}! {bonus_display} earned!\n{bonus_msg}"

def get_daily_bonus_info(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT daily_bonus_claimed, daily_bonus_streak FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    
    if not result or not result[0]:
        return {'can_claim': True, 'streak': 0, 'next': 'Day 1/3 - ₹10 goal'}
    
    try:
        last_claim = datetime.strptime(result[0], '%Y-%m-%d %H:%M:%S')
        streak = safe_int(result[1] or 0)
        
        if (datetime.now() - last_claim).days < 1:
            return {'can_claim': False, 'streak': streak, 'next': f'Day {streak+1}/3 - ₹10 goal'}
        
        return {'can_claim': True, 'streak': streak, 'next': f'Day {streak+1}/3 - ₹10 goal'}
    except:
        return {'can_claim': True, 'streak': 0, 'next': 'Day 1/3 - ₹10 goal'}

# ============ TOP PLAYERS FUNCTIONS ============

def get_top_activity(limit=10):
    """Get top players by daily activity points"""
    conn = get_db()
    c = conn.cursor()
    
    query = '''
        SELECT 
            user_id, 
            username, 
            first_name,
            daily_activity,
            currency,
            wallet_balance_inr,
            wallet_balance_usd
        FROM users
        WHERE daily_activity > 0
        ORDER BY daily_activity DESC
        LIMIT ?
    '''
    
    c.execute(query, (limit,))
    users = c.fetchall()
    conn.close()
    return users

def get_user_activity_rank(user_id):
    """Get user's rank in daily activity"""
    conn = get_db()
    c = conn.cursor()
    
    # Get user's daily activity
    c.execute('SELECT daily_activity FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    if not result:
        conn.close()
        return 0, 0
    
    daily_activity = result[0]
    
    # Count users with higher activity
    c.execute('SELECT COUNT(*) + 1 FROM users WHERE daily_activity > ?', (daily_activity,))
    rank = c.fetchone()[0]
    
    conn.close()
    return rank, daily_activity

# ============ PVP GAME HANDLER ============

class PVPGameHandler:
    def __init__(self):
        self.active_pvp_games = {}
        self.game_buttons = {}
    
    def create_pvp_game(self, game_id, challenger_id, challenged_id, rounds_type, rolls, bet_amount, currency):
        self.active_pvp_games[game_id] = {
            'game_id': game_id,
            'challenger_id': challenger_id,
            'challenged_id': challenged_id,
            'rounds_type': rounds_type,
            'total_rolls': rolls,
            'bet_amount': bet_amount,
            'currency': currency,
            'current_turn': challenger_id,
            'player1_rolls': [],
            'player2_rolls': [],
            'player1_total': 0,
            'player2_total': 0,
            'player1_roll_count': 0,
            'player2_roll_count': 0,
            'is_active': True,
            'game_over': False,
            'result_sent': False,
            'challenger_name': '',
            'challenged_name': '',
            'roll_in_progress': False,
            'group_chat_id': None,
            'message_id': None
        }
        
        self.game_buttons[game_id] = {
            'allowed_user': challenger_id,
            'challenger_id': challenger_id,
            'challenged_id': challenged_id
        }
        
        logging.info(f"PVP Game Created: {game_id}")
        return self.active_pvp_games[game_id]
    
    def get_game(self, game_id):
        return self.active_pvp_games.get(game_id)
    
    def get_user_game(self, user_id):
        for game_id, game in self.active_pvp_games.items():
            if (game['challenger_id'] == user_id or game['challenged_id'] == user_id):
                return game
        return None
    
    def get_other_player(self, game, user_id):
        if game['challenger_id'] == user_id:
            return game['challenged_id']
        return game['challenger_id']
    
    def get_current_player_name(self, game):
        if game['current_turn'] == game['challenger_id']:
            return game.get('challenger_name', 'Player 1')
        return game.get('challenged_name', 'Player 2')
    
    def is_allowed_to_roll(self, game_id, user_id):
        if game_id not in self.game_buttons:
            return False
        return self.game_buttons[game_id]['allowed_user'] == user_id
    
    def set_next_player(self, game_id, next_user_id):
        if game_id in self.game_buttons:
            self.game_buttons[game_id]['allowed_user'] = next_user_id
    
    async def send_telegram_dice(self, bot, chat_id):
        try:
            message = await bot.send_dice(chat_id=chat_id, emoji="🎲")
            return message.dice.value
        except Exception as e:
            logging.error(f"Error sending dice: {e}")
            return random.randint(1, 6)
    
    async def make_roll(self, game_id, user_id, bot, chat_id) -> Dict:
        game = self.active_pvp_games.get(game_id)
        if not game:
            return {'error': 'Game not found!'}
        
        if not game['is_active']:
            return {'error': 'Game is already over!'}
        
        if game['game_over']:
            return {'error': 'Game has ended!'}
        
        if not self.is_allowed_to_roll(game_id, user_id):
            return {'error': f"Not your turn! Only {self.get_current_player_name(game)} can roll."}
        
        if game['current_turn'] != user_id:
            return {'error': f"Not your turn! Only {self.get_current_player_name(game)} can roll."}
        
        if game.get('roll_in_progress', False):
            return {'error': 'Roll in progress! Please wait.'}
        
        game['roll_in_progress'] = True
        
        roll_value = await self.send_telegram_dice(bot, chat_id)
        
        if user_id == game['challenger_id']:
            if game['player1_roll_count'] >= game['total_rolls']:
                game['roll_in_progress'] = False
                return {'error': 'You have completed all your rolls!'}
            game['player1_rolls'].append(roll_value)
            game['player1_total'] += roll_value
            game['player1_roll_count'] += 1
            player_name = game.get('challenger_name', 'Player 1')
        else:
            if game['player2_roll_count'] >= game['total_rolls']:
                game['roll_in_progress'] = False
                return {'error': 'You have completed all your rolls!'}
            game['player2_rolls'].append(roll_value)
            game['player2_total'] += roll_value
            game['player2_roll_count'] += 1
            player_name = game.get('challenged_name', 'Player 2')
        
        player_completed = False
        if user_id == game['challenger_id']:
            if game['player1_roll_count'] >= game['total_rolls']:
                player_completed = True
        else:
            if game['player2_roll_count'] >= game['total_rolls']:
                player_completed = True
        
        dice_emoji = DICE_EMOJIS.get(roll_value, '🎲')
        rolls_so_far = game['player1_rolls'] if user_id == game['challenger_id'] else game['player2_rolls']
        roll_history = ' '.join([f"{DICE_EMOJIS.get(r, '🎲')}" for r in rolls_so_far])
        roll_numbers = f"({', '.join(map(str, rolls_so_far))})"
        total_score = game['player1_total'] if user_id == game['challenger_id'] else game['player2_total']
        
        message = f"🎲 **{player_name} rolled:** {dice_emoji} **{roll_value}**\n\n"
        message += f"📊 **Your rolls:** {roll_history} {roll_numbers}\n"
        message += f"📈 **Total so far:** **{total_score}**\n"
        
        if player_completed:
            message += f"\n✅ **You completed all {game['total_rolls']} rolls!**"
            other_id = self.get_other_player(game, user_id)
            other_rolls = game['player2_roll_count'] if user_id == game['challenger_id'] else game['player1_roll_count']
            
            if other_rolls < game['total_rolls']:
                game['current_turn'] = other_id
                other_name = game.get('challenged_name', 'Player 2') if user_id == game['challenger_id'] else game.get('challenger_name', 'Player 1')
                message += f"\n\n🔄 Now it's **{other_name}'s turn** to roll!"
                game['roll_in_progress'] = False
                
                self.set_next_player(game_id, other_id)
                
                result = {
                    'success': True,
                    'message': message,
                    'roll_value': roll_value,
                    'player_completed': True,
                    'total': total_score,
                    'all_rolls': rolls_so_far,
                    'game_over': False,
                    'switch_turn': True,
                    'next_player_id': other_id,
                    'next_player_name': other_name
                }
            else:
                game['game_over'] = True
                game['is_active'] = False
                game['roll_in_progress'] = False
                result_data = self.get_result(game)
                message += f"\n\n🏆 **GAME OVER!**\n\n"
                message += self.format_result(game, result_data)
                result = {
                    'success': True,
                    'message': message,
                    'roll_value': roll_value,
                    'player_completed': True,
                    'total': total_score,
                    'all_rolls': rolls_so_far,
                    'game_over': True,
                    'result': result_data
                }
        else:
            rolls_left = game['total_rolls'] - (game['player1_roll_count'] if user_id == game['challenger_id'] else game['player2_roll_count'])
            message += f"\n⚡ Rolls left: {rolls_left}"
            game['roll_in_progress'] = False
            result = {
                'success': True,
                'message': message,
                'roll_value': roll_value,
                'player_completed': False,
                'total': total_score,
                'all_rolls': rolls_so_far,
                'game_over': False
            }
        
        return result
    
    def get_result(self, game):
        p1_total = game['player1_total']
        p2_total = game['player2_total']
        p1_rolls = game['player1_rolls']
        p2_rolls = game['player2_rolls']
        bet_amount = game['bet_amount']
        
        total_pot = bet_amount * 2
        platform_fee = int(total_pot * PLATFORM_FEE_PERCENT / 100)
        winner_amount = total_pot - platform_fee
        
        if p1_total > p2_total:
            return {
                'winner': 'player1',
                'winner_id': game['challenger_id'],
                'loser_id': game['challenged_id'],
                'winner_name': game.get('challenger_name', 'Player 1'),
                'loser_name': game.get('challenged_name', 'Player 2'),
                'player1_total': p1_total,
                'player2_total': p2_total,
                'player1_rolls': p1_rolls,
                'player2_rolls': p2_rolls,
                'bet_amount': bet_amount,
                'total_pot': total_pot,
                'platform_fee': platform_fee,
                'winner_amount': winner_amount,
                'currency': game['currency']
            }
        elif p2_total > p1_total:
            return {
                'winner': 'player2',
                'winner_id': game['challenged_id'],
                'loser_id': game['challenger_id'],
                'winner_name': game.get('challenged_name', 'Player 2'),
                'loser_name': game.get('challenger_name', 'Player 1'),
                'player1_total': p1_total,
                'player2_total': p2_total,
                'player1_rolls': p1_rolls,
                'player2_rolls': p2_rolls,
                'bet_amount': bet_amount,
                'total_pot': total_pot,
                'platform_fee': platform_fee,
                'winner_amount': winner_amount,
                'currency': game['currency']
            }
        else:
            return {
                'winner': None,
                'winner_id': None,
                'loser_id': None,
                'winner_name': None,
                'loser_name': None,
                'player1_total': p1_total,
                'player2_total': p2_total,
                'player1_rolls': p1_rolls,
                'player2_rolls': p2_rolls,
                'bet_amount': bet_amount,
                'total_pot': total_pot,
                'currency': game['currency'],
                'is_draw': True
            }
    
    def format_result(self, game, result):
        symbol = '₹' if game['currency'] == 'INR' else '$'
        p1_name = game.get('challenger_name', 'Player 1')
        p2_name = game.get('challenged_name', 'Player 2')
        
        p1_rolls_str = ' '.join([f"{DICE_EMOJIS.get(r, '🎲')}" for r in result['player1_rolls']])
        p1_rolls_num = f"({', '.join(map(str, result['player1_rolls']))})"
        p2_rolls_str = ' '.join([f"{DICE_EMOJIS.get(r, '🎲')}" for r in result['player2_rolls']])
        p2_rolls_num = f"({', '.join(map(str, result['player2_rolls']))})"
        
        message = f"📊 **Final Scores:**\n\n"
        message += f"👤 {p1_name}: **{result['player1_total']}**\n"
        message += f"   {p1_rolls_str} {p1_rolls_num}\n\n"
        message += f"👤 {p2_name}: **{result['player2_total']}**\n"
        message += f"   {p2_rolls_str} {p2_rolls_num}\n\n"
        
        if result.get('winner'):
            winner_name = result['winner_name'] or (p1_name if result['winner'] == 'player1' else p2_name)
            loser_name = result['loser_name'] or (p2_name if result['winner'] == 'player1' else p1_name)
            message += f"🎉 **{winner_name} WINS!** 🎉\n\n"
            message += f"💰 **Each Player Bet:** {symbol}{result['bet_amount']}\n"
            message += f"💰 **Total Pot:** {symbol}{result['total_pot']}\n"
            message += f"🏆 **Winner Gets:** {symbol}{result['winner_amount']}\n"
            message += f"📌 {loser_name} gets: {symbol}0"
        else:
            message += "🤝 **DRAW!**\n"
            message += f"💰 Both players get their money back!"
        
        return message
    
    def end_game(self, game_id):
        if game_id in self.active_pvp_games:
            self.active_pvp_games[game_id]['is_active'] = False
            del self.active_pvp_games[game_id]
        if game_id in self.game_buttons:
            del self.game_buttons[game_id]

pvp_handler = PVPGameHandler()

# ============ GAME MANAGER ============

class GameManager:
    def __init__(self):
        self.active_games = {}
        self.user_games = {}
        self.pending_challenges = {}
        self.challenge_players = {}
    
    def create_game(self, game_type, mode, player1_id, player2_id=None, rolls=3, 
                    bet_amount=0, rounds_type="3r1w", currency='INR'):
        if game_type == 'dice':
            game = DiceGame()
            game.setup_game(rounds_type, rolls, bet_amount, currency)
        elif game_type == 'bowling':
            game = BowlingGame()
        else:
            return {'error': 'Game not found'}
        
        game.mode = mode
        if game_type == 'dice' and bet_amount > 0:
            game.bet_amount = bet_amount
            total_pot = bet_amount * 2
            game.platform_fee = int(total_pot * PLATFORM_FEE_PERCENT / 100)
            game.prize_pool = total_pot - game.platform_fee
        
        result = game.start_game(player1_id, player2_id, rolls if game_type == 'dice' else None)
        game_id = f"{game_type}_{player1_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        self.active_games[game_id] = game
        self.user_games[player1_id] = game_id
        if player2_id:
            self.user_games[player2_id] = game_id
        return {
            'game_id': game_id, 
            'message': result['message'],
            'bet_amount': game.bet_amount,
            'platform_fee': game.platform_fee if hasattr(game, 'platform_fee') else 0,
            'prize_pool': game.prize_pool if hasattr(game, 'prize_pool') else 0,
            'rounds_type': game.rounds_type if hasattr(game, 'rounds_type') else None,
            'max_rolls': game.max_rolls if hasattr(game, 'max_rolls') else 0,
            'currency': game.currency if hasattr(game, 'currency') else 'INR'
        }
    
    def create_challenge(self, game_type, challenger_id, challenged_id, bet_amount, 
                         rounds_type="3r1w", rolls=3, currency='INR', group_chat_id=None):
        challenge_id = f"ch_{datetime.now().strftime('%Y%m%d%H%M%S')}_{random.randint(1000, 9999)}"
        
        challenger_profile = get_user_profile(challenger_id)
        challenger_username = challenger_profile['username'] if challenger_profile else str(challenger_id)
        
        challenged_profile = get_user_profile(challenged_id)
        challenged_username = challenged_profile['username'] if challenged_profile else str(challenged_id)
        
        self.pending_challenges[challenge_id] = {
            'game_type': game_type,
            'challenger_id': challenger_id,
            'challenger_username': challenger_username,
            'challenged_id': challenged_id,
            'challenged_username': challenged_username,
            'bet_amount': bet_amount,
            'rounds_type': rounds_type,
            'rolls': rolls,
            'currency': currency,
            'status': 'pending',
            'created_at': datetime.now(),
            'group_chat_id': group_chat_id
        }
        
        self.challenge_players[challenge_id] = challenged_id
        
        return {'challenge_id': challenge_id}
    
    def accept_challenge(self, challenge_id, player_id, group_chat_id=None):
        if challenge_id not in self.pending_challenges:
            return {'error': 'Challenge not found'}
        
        challenge = self.pending_challenges[challenge_id]
        if challenge['status'] != 'pending':
            return {'error': 'Challenge already handled'}
        
        if challenge['challenged_id'] != player_id:
            return {'error': 'You are not the challenged player'}
        
        result = self.create_game(
            challenge['game_type'],
            'pvp',
            challenge['challenger_id'],
            challenge['challenged_id'],
            challenge.get('rolls', 3),
            challenge.get('bet_amount', 0),
            challenge.get('rounds_type', '3r1w'),
            challenge.get('currency', 'INR')
        )
        
        if 'error' in result:
            return result
        
        p1 = get_user_profile(challenge['challenger_id'])
        p2 = get_user_profile(challenge['challenged_id'])
        
        pvp_game = pvp_handler.create_pvp_game(
            result['game_id'],
            challenge['challenger_id'],
            challenge['challenged_id'],
            challenge.get('rounds_type', '3r1w'),
            challenge.get('rolls', 3),
            challenge.get('bet_amount', 0),
            challenge.get('currency', 'INR')
        )
        
        if p1:
            pvp_game['challenger_name'] = p1['username'] or f"Player{challenge['challenger_id']}"
        else:
            pvp_game['challenger_name'] = f"Player{challenge['challenger_id']}"
        
        if p2:
            pvp_game['challenged_name'] = p2['username'] or f"Player{challenge['challenged_id']}"
        else:
            pvp_game['challenged_name'] = f"Player{challenge['challenged_id']}"
        
        pvp_game['group_chat_id'] = group_chat_id or challenge.get('group_chat_id')
        
        challenge['status'] = 'accepted'
        
        if challenge_id in self.challenge_players:
            del self.challenge_players[challenge_id]
        del self.pending_challenges[challenge_id]
        
        return result
    
    def decline_challenge(self, challenge_id, player_id):
        if challenge_id in self.pending_challenges:
            challenge = self.pending_challenges[challenge_id]
            if challenge['challenged_id'] != player_id:
                return {'error': 'You are not the challenged player'}
            
            challenge['status'] = 'declined'
            currency = challenge.get('currency', 'INR')
            bet_amount = challenge['bet_amount']
            min_balance = bet_amount * 100
            
            update_wallet(challenge['challenger_id'], min_balance, currency)
            update_wallet(challenge['challenged_id'], min_balance, currency)
            
            if challenge_id in self.challenge_players:
                del self.challenge_players[challenge_id]
            del self.pending_challenges[challenge_id]
        return {'message': 'Challenge declined and funds refunded'}
    
    def get_pending_challenge(self, challenge_id):
        return self.pending_challenges.get(challenge_id)
    
    def get_user_pending_challenge(self, user_id):
        for challenge in self.pending_challenges.values():
            if (challenge.get('challenger_id') == user_id or challenge.get('challenged_id') == user_id) and challenge.get('status') == 'pending':
                return challenge
        return None
    
    def get_user_game(self, user_id):
        return self.user_games.get(user_id)
    
    def get_game(self, game_id):
        return self.active_games.get(game_id)
    
    def make_move(self, game_id, player_id):
        if game_id not in self.active_games:
            return {'error': 'Game not found'}
        
        game = self.active_games[game_id]
        success, result = game.make_move(player_id)
        
        if not success:
            return {'error': result['message']}
        
        if 'result' in result and not game.is_active:
            self._handle_game_end(game_id, result['result'])
        
        return result
    
    def _handle_game_end(self, game_id, result):
        game = self.active_games.get(game_id)
        if game:
            if game.mode == 'pvp':
                winner = result.get('winner')
                currency = game.currency
                
                if winner == 'player1':
                    update_user_stats(game.players['player1']['id'], won=True, bet_amount=game.bet_amount, currency=currency, game_type=game.game_type)
                    if game.players['player2']:
                        update_user_stats(game.players['player2']['id'], won=False, bet_amount=game.bet_amount, currency=currency, game_type=game.game_type)
                    
                    prize = game.prize_pool
                    prize_amount = prize * 100
                    update_wallet(game.players['player1']['id'], prize_amount, currency)
                    
                    balance = get_user_balance(game.players['player1']['id'], currency)
                    add_transaction(game.players['player1']['id'], 'won', prize_amount, currency, balance, f"PVP win - {game.game_type}")
                    
                    platform_amount = game.platform_fee * 100
                    admin_profile = get_user_profile(ADMIN_USER_ID)
                    if admin_profile:
                        admin_currency = admin_profile['currency']
                        update_wallet(ADMIN_USER_ID, platform_amount, admin_currency)
                        admin_balance = get_user_balance(ADMIN_USER_ID, admin_currency)
                        add_transaction(ADMIN_USER_ID, 'platform_fee', platform_amount, admin_currency, admin_balance, f"Platform fee from PVP {game.game_type} game")
                    
                    save_game_history({
                        'game_id': game_id,
                        'game_type': game.game_type,
                        'rounds_type': game.rounds_type,
                        'player1_id': game.players['player1']['id'],
                        'player2_id': game.players['player2']['id'] if game.players['player2'] else None,
                        'winner_id': game.players['player1']['id'],
                        'bet_amount': game.bet_amount,
                        'currency': currency,
                        'platform_fee': game.platform_fee,
                        'commission_fee': 0,
                        'winner_amount': prize,
                        'player1_rolls': ','.join(map(str, result['player1_rolls'])),
                        'player2_rolls': ','.join(map(str, result['player2_rolls'])),
                        'player1_total': result['player1_score'],
                        'player2_total': result['player2_score']
                    })
                    
                elif winner == 'player2':
                    if game.players['player2']:
                        update_user_stats(game.players['player1']['id'], won=False, bet_amount=game.bet_amount, currency=currency, game_type=game.game_type)
                        update_user_stats(game.players['player2']['id'], won=True, bet_amount=game.bet_amount, currency=currency, game_type=game.game_type)
                        
                        prize = game.prize_pool
                        prize_amount = prize * 100
                        update_wallet(game.players['player2']['id'], prize_amount, currency)
                        
                        balance = get_user_balance(game.players['player2']['id'], currency)
                        add_transaction(game.players['player2']['id'], 'won', prize_amount, currency, balance, f"PVP win - {game.game_type}")
                        
                        platform_amount = game.platform_fee * 100
                        admin_profile = get_user_profile(ADMIN_USER_ID)
                        if admin_profile:
                            admin_currency = admin_profile['currency']
                            update_wallet(ADMIN_USER_ID, platform_amount, admin_currency)
                            admin_balance = get_user_balance(ADMIN_USER_ID, admin_currency)
                            add_transaction(ADMIN_USER_ID, 'platform_fee', platform_amount, admin_currency, admin_balance, f"Platform fee from PVP {game.game_type} game")
                        
                        save_game_history({
                            'game_id': game_id,
                            'game_type': game.game_type,
                            'rounds_type': game.rounds_type,
                            'player1_id': game.players['player1']['id'],
                            'player2_id': game.players['player2']['id'],
                            'winner_id': game.players['player2']['id'],
                            'bet_amount': game.bet_amount,
                            'currency': currency,
                            'platform_fee': game.platform_fee,
                            'commission_fee': 0,
                            'winner_amount': prize,
                            'player1_rolls': ','.join(map(str, result['player1_rolls'])),
                            'player2_rolls': ','.join(map(str, result['player2_rolls'])),
                            'player1_total': result['player1_score'],
                            'player2_total': result['player2_score']
                        })
                else:
                    # Draw
                    update_user_stats(game.players['player1']['id'], draw=True, bet_amount=0, currency=currency, game_type=game.game_type)
                    if game.players['player2']:
                        update_user_stats(game.players['player2']['id'], draw=True, bet_amount=0, currency=currency, game_type=game.game_type)
                        
                        bet_amount = game.bet_amount * 100
                        update_wallet(game.players['player1']['id'], bet_amount, currency)
                        update_wallet(game.players['player2']['id'], bet_amount, currency)
                        
                        balance1 = get_user_balance(game.players['player1']['id'], currency)
                        balance2 = get_user_balance(game.players['player2']['id'], currency)
                        add_transaction(game.players['player1']['id'], 'draw_refund', bet_amount, currency, balance1, "PVP draw refund")
                        add_transaction(game.players['player2']['id'], 'draw_refund', bet_amount, currency, balance2, "PVP draw refund")
                        
                        save_game_history({
                            'game_id': game_id,
                            'game_type': game.game_type,
                            'rounds_type': game.rounds_type,
                            'player1_id': game.players['player1']['id'],
                            'player2_id': game.players['player2']['id'],
                            'winner_id': None,
                            'bet_amount': game.bet_amount,
                            'currency': currency,
                            'platform_fee': 0,
                            'commission_fee': 0,
                            'winner_amount': 0,
                            'player1_rolls': ','.join(map(str, result['player1_rolls'])),
                            'player2_rolls': ','.join(map(str, result['player2_rolls'])),
                            'player1_total': result['player1_score'],
                            'player2_total': result['player2_score']
                        })
        
        self.end_game(game_id)
    
    def end_game(self, game_id):
        if game_id in self.active_games:
            self.active_games[game_id].reset_game()
            del self.active_games[game_id]
        
        for uid, gid in list(self.user_games.items()):
            if gid == game_id:
                del self.user_games[uid]

game_manager = GameManager()

# ============ SIMPLE GAME CLASSES ============

class DiceGame:
    def __init__(self):
        self.game_type = 'dice'
        self.mode = None
        self.players = {}
        self.is_active = False
        self.current_turn = None
        self.bet_amount = 0
        self.max_rolls = 3
        self.rounds_type = "3r1w"
        self.currency = "INR"
        self.platform_fee = 0
        self.prize_pool = 0
        self.player1_username = "Player 1"
        self.player2_username = "Player 2"
    
    def setup_game(self, rounds_type, rolls, bet_amount, currency):
        self.rounds_type = rounds_type
        self.max_rolls = rolls
        self.bet_amount = bet_amount
        self.currency = currency
        total_pot = bet_amount * 2
        self.platform_fee = int(total_pot * PLATFORM_FEE_PERCENT / 100)
        self.prize_pool = total_pot - self.platform_fee if bet_amount > 0 else 0
        return self
    
    def start_game(self, player1_id, player2_id=None, rolls=3):
        self.max_rolls = rolls
        self.players = {
            'player1': {'id': player1_id, 'score': 0, 'rolls_left': self.max_rolls, 'rolls': []},
            'player2': {'id': player2_id, 'score': 0, 'rolls_left': self.max_rolls, 'rolls': []} if player2_id else None
        }
        self.current_turn = 'player1'
        self.is_active = True
        return {'message': f"🎲 Dice Game! {self.max_rolls} rolls each."}
    
    def make_move(self, player_id):
        if not self.is_active:
            return False, {'message': 'Game over!'}
        
        current = None
        if self.players['player1']['id'] == player_id:
            current = 'player1'
        elif self.players['player2'] and self.players['player2']['id'] == player_id:
            current = 'player2'
        
        if not current or current != self.current_turn:
            return False, {'message': 'Not your turn!'}
        
        if self.players[current]['rolls_left'] <= 0:
            return False, {'message': 'No rolls left!'}
        
        roll = random.randint(1, 6)
        self.players[current]['score'] += roll
        self.players[current]['rolls_left'] -= 1
        self.players[current]['rolls'].append(roll)
        
        if self.players[current]['rolls_left'] <= 0:
            if self.mode == 'pvp' and current == 'player1' and self.players['player2']:
                self.current_turn = 'player2'
                return True, {'message': f"🎲 Rolled: {roll}\nTotal: {self.players[current]['score']}\nRolls: {', '.join(map(str, self.players[current]['rolls']))}\n\nNow Player 2's turn!"}
            else:
                self.is_active = False
                result = self.get_result()
                return True, {'message': self._format_result(result), 'result': result}
        
        return True, {'message': f"🎲 Rolled: {roll}\nTotal: {self.players[current]['score']}\nRolls: {', '.join(map(str, self.players[current]['rolls']))}\nRolls left: {self.players[current]['rolls_left']}"}
    
    def get_result(self):
        if self.mode == 'pvp' and self.players['player2']:
            p1 = self.players['player1']['score']
            p2 = self.players['player2']['score']
            p1_rolls = self.players['player1']['rolls']
            p2_rolls = self.players['player2']['rolls']
            total_pot = self.bet_amount * 2
            
            if p1 > p2:
                return {
                    'winner': 'player1',
                    'winner_id': self.players['player1']['id'],
                    'loser_id': self.players['player2']['id'],
                    'player1_score': p1,
                    'player2_score': p2,
                    'player1_rolls': p1_rolls,
                    'player2_rolls': p2_rolls,
                    'bet_amount': self.bet_amount,
                    'total_pot': total_pot,
                    'platform_fee': self.platform_fee,
                    'prize_pool': self.prize_pool,
                    'currency': self.currency
                }
            elif p2 > p1:
                return {
                    'winner': 'player2',
                    'winner_id': self.players['player2']['id'],
                    'loser_id': self.players['player1']['id'],
                    'player1_score': p1,
                    'player2_score': p2,
                    'player1_rolls': p1_rolls,
                    'player2_rolls': p2_rolls,
                    'bet_amount': self.bet_amount,
                    'total_pot': total_pot,
                    'platform_fee': self.platform_fee,
                    'prize_pool': self.prize_pool,
                    'currency': self.currency
                }
            else:
                return {
                    'winner': None,
                    'winner_id': None,
                    'loser_id': None,
                    'player1_score': p1,
                    'player2_score': p2,
                    'player1_rolls': p1_rolls,
                    'player2_rolls': p2_rolls,
                    'bet_amount': self.bet_amount,
                    'currency': self.currency,
                    'is_draw': True
                }
        return {'scores': {'player': self.players['player1']['score']}, 'winner': 'player'}
    
    def _format_result(self, result):
        if self.mode == 'pvp' and self.players['player2']:
            symbol = '₹' if self.currency == 'INR' else '$'
            p1_name = self.player1_username
            p2_name = self.player2_username
            p1_rolls = ', '.join(map(str, result['player1_rolls']))
            p2_rolls = ', '.join(map(str, result['player2_rolls']))
            
            message = f"🏆 Game Over!\n\n"
            message += f"👤 {p1_name}: {result['player1_score']} ({p1_rolls})\n"
            message += f"👤 {p2_name}: {result['player2_score']} ({p2_rolls})\n\n"
            
            if result.get('winner'):
                winner_name = p1_name if result['winner'] == 'player1' else p2_name
                message += f"🎉 {winner_name} WINS! 🎉\n"
                if result.get('prize_pool', 0) > 0:
                    message += f"💰 Total Pot: {symbol}{result['total_pot']}\n"
                    message += f"💰 Prize: {symbol}{result['prize_pool']}"
            else:
                message += "🤝 DRAW!\n💰 Both players get their money back!"
            
            return message
        return f"🏆 Your score: {result['scores']['player']}"
    
    def reset_game(self):
        self.players = {}
        self.is_active = False

class BowlingGame:
    def __init__(self):
        self.game_type = 'bowling'
        self.mode = None
        self.players = {}
        self.is_active = False
        self.current_turn = None
        self.bet_amount = 0
        self.frames = 10
        self.current_frame = {}
        self.pins_left = {}
        self.rolls_in_frame = {}
    
    def start_game(self, player1_id, player2_id=None):
        self.players = {
            'player1': {'id': player1_id, 'score': 0, 'rolls': []},
            'player2': {'id': player2_id, 'score': 0, 'rolls': []} if player2_id else None
        }
        self.current_turn = 'player1'
        self.is_active = True
        self.current_frame = {'player1': 0, 'player2': 0 if player2_id else 0}
        self.pins_left = {'player1': 10, 'player2': 10 if player2_id else 10}
        self.rolls_in_frame = {'player1': 0, 'player2': 0 if player2_id else 0}
        return {'message': "🎳 Bowling Game!\n10 frames, 2 rolls each frame."}
    
    def make_move(self, player_id):
        if not self.is_active:
            return False, {'message': 'Game over!'}
        
        current = None
        if self.players['player1']['id'] == player_id:
            current = 'player1'
        elif self.players['player2'] and self.players['player2']['id'] == player_id:
            current = 'player2'
        
        if not current or current != self.current_turn:
            return False, {'message': 'Not your turn!'}
        
        if self.current_frame[current] >= self.frames:
            return False, {'message': 'Game completed!'}
        
        pins = random.randint(0, self.pins_left[current])
        self.players[current]['score'] += pins
        self.pins_left[current] -= pins
        self.rolls_in_frame[current] += 1
        self.players[current]['rolls'].append(pins)
        
        frame_complete = False
        if self.pins_left[current] == 0 or self.rolls_in_frame[current] >= 2:
            frame_complete = True
            self.current_frame[current] += 1
            self.pins_left[current] = 10
            self.rolls_in_frame[current] = 0
        
        if self.current_frame[current] >= self.frames:
            self.is_active = False
            result = self.get_result()
            return True, {'message': self._format_result(result), 'result': result}
        
        if self.mode == 'pvp':
            if frame_complete or current == 'player1':
                self.current_turn = 'player2' if current == 'player1' else 'player1'
        
        return True, {'message': f"🎳 Knocked: {pins} pins\nScore: {self.players[current]['score']}\nFrame: {self.current_frame[current]+1}/{self.frames}"}
    
    def get_result(self):
        if self.mode == 'pvp':
            p1 = self.players['player1']['score']
            p2 = self.players['player2']['score']
            return {'scores': {'player1': p1, 'player2': p2}, 'winner': 'player1' if p1 > p2 else 'player2' if p2 > p1 else None}
        return {'scores': {'player': self.players['player1']['score']}, 'winner': 'player'}
    
    def _format_result(self, result):
        if self.mode == 'pvp':
            return f"🏆 Game Over!\n\nPlayer 1: {result['scores']['player1']}\nPlayer 2: {result['scores']['player2']}\n{'Winner: Player ' + result['winner'] if result['winner'] else 'Draw!'}"
        return f"🏆 Your final score: {result['scores']['player']}"
    
    def reset_game(self):
        self.players = {}
        self.is_active = False

# ============ PROFILE COMMANDS ============

@private_only
async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show simplified user profile - Only Badges"""
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
    
    user_id = user.id
    profile = get_user_profile(user_id)
    
    if not profile:
        await message.reply_text("❌ Profile not found!")
        return
    
    currency = profile['currency']
    symbol = '₹' if currency == 'INR' else '$'
    balance = get_user_balance(user_id, currency) / 100
    is_admin = "👑" if user_id == ADMIN_USER_ID else ""
    username_display = f"@{user.username}" if user.username else profile['username']
    
    # Get level info
    xp = profile.get('experience', 0)
    level_info = get_level_info(xp)
    level = level_info["level"]
    level_badge = level_info["badge"]
    level_name = level_info["name"]
    
    # Get stats
    total_games = profile.get('total_games', 0)
    total_wins = profile.get('total_wins', 0)
    win_streak = profile.get('win_streak', 0)
    rating = profile.get('rating', 0)
    
    # Get daily bonus info
    bonus_info = get_daily_bonus_info(user_id)
    bonus_status = "✅ Claim Now!" if bonus_info['can_claim'] else f"⏳ Day {bonus_info['streak']+1}/3"
    
    # Simplified profile display
    text = f"""
{get_brand_header()}

👤 {username_display} {is_admin}

💰 Balance: {symbol}{balance:.2f}
🌐 Currency: {currency}

🎁 Daily Bonus: {bonus_status}
🔥 Streak: {win_streak} wins

🏆 Games: {total_games} | Wins: {total_wins}
⭐ Rating: {rating}
{level_badge} Level: {level} - {level_name}
💡 XP: {xp}
    """
    
    keyboard = [
        [InlineKeyboardButton("🏅 Badges", callback_data="badges")],
        [InlineKeyboardButton("🔙 Back to Main", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if edit_mode and message:
        try:
            await message.edit_text(text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error editing profile: {e}")
            await message.reply_text(text, reply_markup=reply_markup)
    else:
        await message.reply_text(text, reply_markup=reply_markup)

@private_only
async def badges_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user badges"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    profile = get_user_profile(user_id)
    
    if not profile:
        await query.edit_message_text("❌ Profile not found!")
        return
    
    badges = profile.get('badges', [])
    
    badge_icons = {
        'first_win': '🎯', 'win_streak_5': '🔥', 'win_streak_10': '💪',
        'level_10': '🌟', 'level_25': '⭐', 'level_50': '👑',
        'games_100': '🎮', 'games_500': '🎯', 'games_1000': '🏆',
        'deposit_first': '💰', 'referral_1': '🤝', 'referral_5': '👥'
    }
    
    badge_names = {
        'first_win': 'First Win', 'win_streak_5': 'Win Streak 5', 'win_streak_10': 'Win Streak 10',
        'level_10': 'Level 10', 'level_25': 'Level 25', 'level_50': 'Level 50',
        'games_100': '100 Games', 'games_500': '500 Games', 'games_1000': '1000 Games',
        'deposit_first': 'First Deposit', 'referral_1': 'First Referral', 'referral_5': '5 Referrals'
    }
    
    text = f"""
{get_brand_header()}

⭐ BADGES

Total Badges: {len(badges)}/12
"""
    
    if badges:
        for badge in badges:
            icon = badge_icons.get(badge, '🏅')
            name = badge_names.get(badge, badge.replace('_', ' ').title())
            text += f"\n{icon} {name}"
    else:
        text += "\n\n📌 No badges earned yet."
        text += "\n\n💡 How to earn badges:"
        text += "\n• 🎯 First Win - Win your first game"
        text += "\n• 🔥 Win Streak 5 - Win 5 games in a row"
        text += "\n• 💪 Win Streak 10 - Win 10 games in a row"
        text += "\n• 🌟 Level 10 - Reach level 10"
        text += "\n• ⭐ Level 25 - Reach level 25"
        text += "\n• 👑 Level 50 - Reach level 50"
        text += "\n• 🎮 100 Games - Play 100 games"
        text += "\n• 🎯 500 Games - Play 500 games"
        text += "\n• 🏆 1000 Games - Play 1000 games"
        text += "\n• 💰 First Deposit - Make your first deposit"
        text += "\n• 🤝 First Referral - Get your first referral"
        text += "\n• 👥 5 Referrals - Get 5 referrals"
    
    keyboard = [[InlineKeyboardButton("🔙 Back to Profile", callback_data="profile")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup)

# ============ TOP PLAYERS COMMANDS ============

@private_only
async def top_players_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show top players menu - Only Activity"""
    query = update.callback_query
    if query:
        await query.answer()
        message = query.message
        edit_mode = True
    else:
        message = update.message
        edit_mode = False
    
    keyboard = [
        [InlineKeyboardButton("🏆 Top Activity (Daily)", callback_data="top_activity")],
        [InlineKeyboardButton("🔙 Back to Main", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = f"""
{get_brand_header()}

🏆 **TOP PLAYERS**

🏆 **Top Activity** - Most active players today

Players are ranked by daily activity points.
    """
    
    if edit_mode and message:
        await message.edit_text(text, reply_markup=reply_markup)
    else:
        await message.reply_text(text, reply_markup=reply_markup)

@private_only
async def top_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show top players by daily activity with correct wallet amounts"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    top_users = get_top_activity(10)
    
    if not top_users:
        await query.edit_message_text(
            f"""
{get_brand_header()}

📊 **No activity data found**

Play games to earn activity points!
            """
        )
        return
    
    text = f"""
{get_brand_header()}

🏆 **Activity Top (Daily)**

"""
    
    emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    
    for idx, user in enumerate(top_users, 1):
        user_id = user[0]
        username = user[1] or user[2] or f"User{user_id}"
        daily_activity = user[3]
        currency = user[4] or 'INR'
        symbol = '₹' if currency == 'INR' else '$'
        
        # Get wallet balance correctly from database
        if currency == 'INR':
            wallet_balance = (user[5] if len(user) > 5 else 0) / 100
        else:
            wallet_balance = (user[6] if len(user) > 6 else 0) / 100
        
        emoji = emojis[idx - 1] if idx <= len(emojis) else f"{idx}."
        text += f"\n{emoji} {username} — {daily_activity} pts · {symbol}{wallet_balance:,.2f}"
    
    # Get user's rank
    rank, daily_activity = get_user_activity_rank(user_id)
    
    if rank > 0:
        profile = get_user_profile(user_id)
        currency = profile['currency'] if profile else 'INR'
        symbol = '₹' if currency == 'INR' else '$'
        balance = get_user_balance(user_id, currency) / 100
        text += f"\n\nYour place: #{rank}, {daily_activity} pts · {symbol}{balance:,.2f}"
    else:
        text += "\n\n📌 Play games to earn activity points!"
    
    keyboard = [
        [InlineKeyboardButton("🔄 Refresh", callback_data="top_activity")],
        [InlineKeyboardButton("🔙 Back", callback_data="top_players_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup)

# ============ SETTINGS COMMANDS ============

@private_only
async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show settings menu"""
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
    
    profile = get_user_profile(user.id)
    if not profile:
        await message.reply_text("❌ Profile not found!")
        return
    
    currency = profile['currency']
    symbol = '₹' if currency == 'INR' else '$'
    badges = profile.get('badges', [])
    
    keyboard = [
        [InlineKeyboardButton("💱 Currency", callback_data="settings_currency")],
        [InlineKeyboardButton("🔙 Back to Main", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = f"""
{get_brand_header()}

⚙️ SETTINGS

💱 Currency: {currency} ({symbol})

🏅 Badges: {len(badges)} earned

📌 Your Stats:
🎮 Games: {profile['total_games']}
🏆 Wins: {profile['total_wins']}
⭐ Rating: {profile['rating']}
📊 Level: {profile['level']}
    """
    
    if edit_mode and message:
        await message.edit_text(text, reply_markup=reply_markup)
    else:
        await message.reply_text(text, reply_markup=reply_markup)

@private_only
async def settings_currency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Change currency in settings"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🇮🇳 INR (₹)", callback_data="currency_INR")],
        [InlineKeyboardButton("🇺🇸 USD ($)", callback_data="currency_USD")],
        [InlineKeyboardButton("🔙 Back to Settings", callback_data="settings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"""
{get_brand_header()}

💱 **Change Currency**

Select your preferred currency:

🇮🇳 INR - Indian Rupee
🇺🇸 USD - US Dollar

⚠️ Your wallet balance will remain in the same currency.
Only future transactions will use the new currency.
        """,
        reply_markup=reply_markup
    )

# ============ LOGGING ============

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============ BOT HANDLERS ============

@private_only
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command - Main menu"""
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
        if edit_mode:
            await message.edit_text("❌ Error loading profile.")
        else:
            await message.reply_text("❌ Error loading profile.")
        return
    
    if not profile['currency']:
        keyboard = [[InlineKeyboardButton("🇮🇳 INR (₹)", callback_data="currency_INR"), InlineKeyboardButton("🇺🇸 USD ($)", callback_data="currency_USD")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        if edit_mode:
            await message.edit_text("🌍 Select your currency:", reply_markup=reply_markup)
        else:
            await message.reply_text("🌍 Select your currency:", reply_markup=reply_markup)
        return
    
    currency = profile['currency']
    symbol = '₹' if currency == 'INR' else '$'
    balance = get_user_balance(user.id, currency) / 100
    is_admin = "👑" if user.id == ADMIN_USER_ID else ""
    username_display = f"@{user.username}" if user.username else first_name
    
    # Get level info
    xp = profile.get('experience', 0)
    level_info = get_level_info(xp)
    level = level_info["level"]
    level_badge = level_info["badge"]
    level_name = level_info["name"]
    
    pvp_game = pvp_handler.get_user_game(user.id)
    pending_text = ""
    
    if pvp_game:
        if pvp_game.get('is_active') and not pvp_game.get('game_over'):
            if pvp_game.get('current_turn') == user.id:
                pending_text = "🎯 IT'S YOUR TURN! Click the roll button below!"
            else:
                current_player_name = pvp_handler.get_current_player_name(pvp_game)
                pending_text = f"⏳ Waiting for {current_player_name} to roll..."
        else:
            if pvp_game.get('game_over'):
                pending_text = "🏁 Game has ended! Start a new game."
                pvp_handler.end_game(pvp_game.get('game_id'))
                game_manager.end_game(pvp_game.get('game_id'))
    
    bonus_info = get_daily_bonus_info(user.id)
    bonus_status = "✅ Claim Now!" if bonus_info['can_claim'] else f"⏳ Day {bonus_info['streak']+1}/3"
    
    streak_display = f"🔥 {profile.get('win_streak', 0)} wins" if profile.get('win_streak', 0) > 0 else "No active streak"
    
    keyboard = [
        [InlineKeyboardButton("🎮 Play", callback_data="play")],
        [InlineKeyboardButton("👤 Profile", callback_data="profile")],
        [InlineKeyboardButton("💰 Balance", callback_data="balance")],
        [InlineKeyboardButton("🎁 Bonus", callback_data="daily_bonus_menu")],
        [InlineKeyboardButton("🏆 Top Players", callback_data="top_players_menu")],
        [InlineKeyboardButton("📜 History", callback_data="history")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="settings")],
        [InlineKeyboardButton("💳 Payments", callback_data="payment_menu")],
        [InlineKeyboardButton("❓ Help", callback_data="help")]
    ]
    
    if is_admin:
        keyboard.append([InlineKeyboardButton("👑 Admin Panel", callback_data="admin_panel")])
    
    if pvp_game and pvp_game.get('is_active') and not pvp_game.get('game_over'):
        if pvp_game.get('current_turn') == user.id:
            keyboard.insert(0, [InlineKeyboardButton("🎲 ROLL DICE NOW!", callback_data=f"pvp_roll_{pvp_game['game_id']}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    profile_text = f"""
{get_brand_header()}

👤 {username_display} {is_admin}

💰 Balance: {symbol}{balance:.2f}
🌐 Currency: {currency}

🎁 Daily Bonus: {bonus_status}
🔥 Streak: {streak_display}

🏆 Games: {profile['total_games']}
⭐ Rating: {profile['rating']}
{level_badge} Level: {level} - {level_name}
💡 XP: {xp}

{pending_text}

📌 Use /help to see all commands
    """
    
    if edit_mode and message:
        try:
            await message.edit_text(profile_text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error editing message: {e}")
            await message.reply_text(profile_text, reply_markup=reply_markup)
    else:
        await message.reply_text(profile_text, reply_markup=reply_markup)

@private_only
async def play_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show game selection menu"""
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
    
    keyboard = [
        [InlineKeyboardButton("🎲 Challenge Player", callback_data="challenge_step1")],
        [InlineKeyboardButton("🤖 Bot Game", callback_data="bot_menu")],
        [InlineKeyboardButton("🔙 Back to Main", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = f"""
{get_brand_header()}

🎮 **GAME SELECTION**

Select a game mode:

🎲 **Challenge Player** - Play PVP with friends
🤖 **Bot Game** - Play against AI

📌 **How to Play:**
1. Select challenge or bot game
2. Set bet amount and rounds
3. Roll the dice!
4. Highest total wins!

💡 Each game gives activity points!
    """
    
    if edit_mode and message:
        await message.edit_text(text, reply_markup=reply_markup)
    else:
        await message.reply_text(text, reply_markup=reply_markup)

@private_only
async def bot_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🎲 Dice", callback_data="game_type_dice_bot")],
        [InlineKeyboardButton("🔙 Back to Play", callback_data="play")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"""
{get_brand_header()}

🤖 **BOT GAME**

Select game to play against AI:

🎲 Dice - Roll and win!
Entry: ₹10
Prize: ₹17 (85% of pot)
        """,
        reply_markup=reply_markup
    )

@private_only
async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data_parts = query.data.split('_')
    if len(data_parts) < 3:
        await query.edit_message_text("Invalid selection.")
        return
    
    game_type = data_parts[2]
    mode = data_parts[3]
    user_id = update.effective_user.id
    
    if mode == 'bot':
        currency = get_user_currency(user_id)
        balance = get_user_balance(user_id, currency)
        
        if balance < 1000:
            symbol = '₹' if currency == 'INR' else '$'
            await query.edit_message_text(f"❌ Need minimum {symbol}10 to play!\n\nYour balance: {symbol}{balance/100:.2f}")
            return
        
        update_wallet(user_id, -1000, currency)
        balance = get_user_balance(user_id, currency)
        add_transaction(user_id, 'game_entry', -1000, currency, balance, f"Bot game entry - {game_type}")
        
        result = game_manager.create_game(game_type, mode, user_id, None, 3, 10, "3r1w", currency)
        if 'error' in result:
            await query.edit_message_text(f"❌ {result['error']}")
            return
        
        await query.edit_message_text(
            f"""
{get_brand_header()}

🤖 GAME STARTED!

Use /roll to play!
            """
        )
    else:
        result = game_manager.create_game(game_type, mode, user_id)
        if 'error' in result:
            await query.edit_message_text(f"❌ {result['error']}")
            return
        
        await query.edit_message_text(
            f"""
{get_brand_header()}

👤 GAME STARTED!

Use /roll to play!
            """
        )

# ============ CHALLENGE COMMANDS ============

@private_only
async def challenge_step1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    currency = get_user_currency(user_id)
    symbol = '₹' if currency == 'INR' else '$'
    
    pending = game_manager.get_user_pending_challenge(user_id)
    if pending:
        await query.edit_message_text(
            f"""
{get_brand_header()}

⏳ **You have a pending challenge!**

You already have a challenge pending.
Please wait for it to be accepted or declined.
            """
        )
        return
    
    pvp_game = pvp_handler.get_user_game(user_id)
    if pvp_game and pvp_game['is_active'] and not pvp_game['game_over']:
        await query.edit_message_text(
            f"""
{get_brand_header()}

❌ **You are already in a game!**

Please finish your current game first.
            """
        )
        return
    
    keyboard = []
    bet_amounts = INR_BET_AMOUNTS if currency == 'INR' else USD_BET_AMOUNTS
    
    row = []
    for i, amount in enumerate(bet_amounts):
        row.append(InlineKeyboardButton(f"{symbol}{amount}", callback_data=f"challenge_bet_{amount}"))
        if (i + 1) % 3 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("✏️ Custom Amount", callback_data="challenge_custom_bet")])
    keyboard.append([InlineKeyboardButton("🔙 Back to Main", callback_data="back_to_main")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = f"""
{get_brand_header()}

💰 **STEP 1: Select Bet Amount**

Select how much each player will bet:

💰 Currency: {currency}
📌 Min: {symbol}{min(bet_amounts)}
📌 Max: {symbol}{max(bet_amounts)}

💡 Winner gets the total pot!
    """
    
    await query.edit_message_text(text, reply_markup=reply_markup)

@private_only
async def challenge_bet_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "challenge_custom_bet":
        # Clear any existing state and set awaiting flag
        context.user_data['awaiting_custom_bet'] = True
        context.user_data['challenge_bet'] = None
        context.user_data['challenge_currency'] = get_user_currency(update.effective_user.id)
        
        await query.edit_message_text(
            f"""
{get_brand_header()}

✏️ **Custom Bet Amount**

Please send the bet amount as a message.

📌 Valid amounts:
• INR: 5 - 200
• USD: 1 - 10

Example: Send `75` for ₹75

⏳ You have 60 seconds to respond.
            """
        )
        return
    
    bet_amount = int(data.replace('challenge_bet_', ''))
    context.user_data['challenge_bet'] = bet_amount
    context.user_data['challenge_currency'] = get_user_currency(update.effective_user.id)
    context.user_data['awaiting_custom_bet'] = False
    
    await challenge_step2(update, context)

@private_only
async def challenge_custom_bet_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle custom bet amount input - FIXED"""
    # Check if we're expecting a custom bet
    if not context.user_data.get('awaiting_custom_bet'):
        return
    
    try:
        # Get the message text
        text = update.message.text.strip()
        amount = int(text)
        
        if amount <= 0:
            await update.message.reply_text("❌ Amount must be greater than 0!")
            return
        
        currency = context.user_data.get('challenge_currency', get_user_currency(update.effective_user.id))
        
        # Set max based on currency
        if currency == 'INR':
            max_amount = 200
            min_amount = 5
        else:
            max_amount = 10
            min_amount = 1
        
        if amount > max_amount:
            await update.message.reply_text(f"❌ Maximum amount is {max_amount} for {currency}!")
            return
        
        if amount < min_amount:
            await update.message.reply_text(f"❌ Minimum amount is {min_amount} for {currency}!")
            return
        
        # Store the custom bet
        context.user_data['challenge_bet'] = amount
        context.user_data['challenge_currency'] = currency
        context.user_data['awaiting_custom_bet'] = False
        
        # Send confirmation and proceed to step 2
        await update.message.reply_text(f"✅ Custom bet of {currency} {amount} set!")
        
        # Create a fake query to continue the flow
        class FakeQuery:
            def __init__(self, message):
                self.message = message
            async def edit_message_text(self, text, reply_markup=None):
                await self.message.reply_text(text, reply_markup=reply_markup)
            async def answer(self):
                pass
        
        fake_query = FakeQuery(update.message)
        update.callback_query = fake_query
        
        await challenge_step2(update, context)
        
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number!\n\nExample: 75")

@private_only
async def challenge_step2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    bet_amount = context.user_data.get('challenge_bet', 10)
    currency = context.user_data.get('challenge_currency', 'INR')
    symbol = '₹' if currency == 'INR' else '$'
    
    keyboard = []
    for option in ROUNDS_OPTIONS:
        keyboard.append([InlineKeyboardButton(
            f"🎲 {option['label']}", 
            callback_data=f"challenge_rounds_{option['key']}"
        )])
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="challenge_step1")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = f"""
{get_brand_header()}

🎯 **STEP 2: Select Rounds**

Each Player Bet: {symbol}{bet_amount}
Total Pot: {symbol}{bet_amount * 2}

Choose how many rolls each player gets:

• 2R1W - 2 rolls, highest total wins
• 3R1W - 3 rolls, highest total wins
• 4R1W - 4 rolls, highest total wins
• 5R1W - 5 rolls, highest total wins

💰 Winner gets the total pot!
    """
    
    await query.edit_message_text(text, reply_markup=reply_markup)

@private_only
async def challenge_rounds_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    rounds_key = query.data.replace('challenge_rounds_', '')
    
    rounds_detail = next((r for r in ROUNDS_OPTIONS if r['key'] == rounds_key), None)
    rolls = rounds_detail['rolls'] if rounds_detail else 3
    
    context.user_data['challenge_rounds'] = rounds_key
    context.user_data['challenge_rolls'] = rolls
    
    await challenge_step3(update, context)

@private_only
async def challenge_step3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    bet_amount = context.user_data.get('challenge_bet', 10)
    rounds_key = context.user_data.get('challenge_rounds', '3r1w')
    rolls = context.user_data.get('challenge_rolls', 3)
    currency = context.user_data.get('challenge_currency', 'INR')
    symbol = '₹' if currency == 'INR' else '$'
    
    keyboard = [
        [InlineKeyboardButton("🔙 Back", callback_data="challenge_step2")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = f"""
{get_brand_header()}

👥 **STEP 3: Challenge a Player**

📋 **Your Challenge Details:**
💰 Each Player Bet: {symbol}{bet_amount}
💰 Total Pot: {symbol}{bet_amount * 2}
📋 Rounds: {rounds_key.upper()} ({rolls} rolls each)
🌐 Currency: {currency}

To challenge someone, type:
`/challenge @username`

Example: `/challenge @john`

💡 The challenged player will get a button to accept/decline.
⏳ They have 2 minutes to respond.
    """
    
    await query.edit_message_text(text, reply_markup=reply_markup)

# ============ CHALLENGE COMMAND ============

@private_only
async def challenge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    bet_amount = context.user_data.get('challenge_bet')
    rounds_key = context.user_data.get('challenge_rounds')
    rolls = context.user_data.get('challenge_rolls', 3)
    currency = context.user_data.get('challenge_currency', 'INR')
    
    if not bet_amount or not rounds_key:
        await update.message.reply_text(
            f"""
{get_brand_header()}

❌ **Please complete the challenge setup first!**

Use /start and click "Challenge Player" to set up your challenge.
            """
        )
        return
    
    if len(context.args) < 1:
        await update.message.reply_text(
            f"""
{get_brand_header()}

❌ **Usage:** /challenge @username

Example: /challenge @john

💡 Make sure you've selected bet and rounds first!
            """
        )
        return
    
    mentioned = context.args[0].replace('@', '')
    
    try:
        target = None
        
        try:
            async for member in context.bot.get_chat_members(chat_id):
                if member.user.username and member.user.username.lower() == mentioned.lower():
                    target = member.user
                    break
                elif member.user.first_name.lower() == mentioned.lower():
                    target = member.user
                    break
        except:
            pass
        
        if not target:
            try:
                target = await context.bot.get_user_by_username(mentioned)
            except:
                pass
        
        if not target:
            conn = get_db()
            c = conn.cursor()
            c.execute('SELECT user_id, first_name FROM users WHERE LOWER(username) = ?', (mentioned.lower(),))
            result = c.fetchone()
            conn.close()
            
            if result:
                try:
                    target = await context.bot.get_chat(result[0])
                except:
                    class FakeUser:
                        def __init__(self, id, username, first_name):
                            self.id = id
                            self.username = username
                            self.first_name = first_name
                            self.last_name = ""
                    target = FakeUser(result[0], mentioned, result[1] or mentioned)
        
        if not target:
            await update.message.reply_text(
                f"""
❌ **User @{mentioned} not found!**

💡 Make sure:
1. @{mentioned} is in this group
2. @{mentioned} has started the bot with /start
3. You typed the username correctly
                """
            )
            return
        
        if target.id == user_id:
            await update.message.reply_text("❌ You cannot challenge yourself!")
            return
        
        symbol = '₹' if currency == 'INR' else '$'
        
        get_or_create_user(
            target.id, 
            target.username or mentioned, 
            target.first_name or "User", 
            target.last_name if hasattr(target, 'last_name') else ""
        )
        
        bal1 = get_user_balance(user_id, currency)
        bal2 = get_user_balance(target.id, currency)
        min_balance = bet_amount * 100
        
        if bal1 < min_balance:
            await update.message.reply_text(f"❌ You need {symbol}{bet_amount} to play!\nYour balance: {symbol}{bal1/100:.2f}")
            return
        
        if bal2 < min_balance:
            await update.message.reply_text(
                f"""
❌ @{mentioned} doesn't have enough balance!

Their balance: {symbol}{bal2/100:.2f}
Need: {symbol}{bet_amount}

💡 Ask them to deposit or play games to earn balance.
                """
            )
            return
        
        update_wallet(user_id, -min_balance, currency)
        update_wallet(target.id, -min_balance, currency)
        
        balance = get_user_balance(user_id, currency)
        add_transaction(user_id, 'bet_hold', -min_balance, currency, balance, f"PVP bet hold - dice")
        balance2 = get_user_balance(target.id, currency)
        add_transaction(target.id, 'bet_hold', -min_balance, currency, balance2, f"PVP bet hold - dice")
        
        result = game_manager.create_challenge(
            'dice', user_id, target.id, bet_amount, 
            rounds_key, rolls, currency, chat_id
        )
        
        if 'error' in result:
            update_wallet(user_id, min_balance, currency)
            update_wallet(target.id, min_balance, currency)
            await update.message.reply_text(f"❌ {result['error']}")
            return
        
        challenge_id = result['challenge_id']
        sender_name = update.effective_user.username or update.effective_user.first_name
        target_name = target.username or target.first_name or mentioned
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Accept", callback_data=f"accept_{challenge_id}"),
                InlineKeyboardButton("❌ Decline", callback_data=f"decline_{challenge_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        challenge_text = f"""
{get_brand_header()}

⚔️ **CHALLENGE!**

From: @{sender_name}
To: @{target_name}
Game: Dice PVP
Each Player Bet: {symbol}{bet_amount}
Total Pot: {symbol}{bet_amount * 2}
Rounds: {rounds_key.upper()} ({rolls} rolls each)

💰 Winner gets the total pot!

⏳ You have 2 minutes to accept!

@{target_name}, do you accept?
        """
        
        await context.bot.send_message(
            chat_id=chat_id,
            text=challenge_text,
            reply_markup=reply_markup
        )
        
        await update.message.reply_text(f"✅ Challenge sent to @{target_name}!\n\n⏳ They have 2 minutes to accept.")
        
        context.user_data.pop('challenge_bet', None)
        context.user_data.pop('challenge_rounds', None)
        context.user_data.pop('challenge_rolls', None)
        context.user_data.pop('challenge_currency', None)
        context.user_data.pop('awaiting_custom_bet', None)
        
        async def auto_decline():
            await asyncio.sleep(CHALLENGE_TIMEOUT)
            challenge = game_manager.get_pending_challenge(challenge_id)
            if challenge and challenge['status'] == 'pending':
                game_manager.decline_challenge(challenge_id, target.id)
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"""
{get_brand_header()}

⏳ **Challenge Timed Out!**

@{target_name} didn't accept the challenge in time.

💰 Funds have been refunded to both players.
                    """
                )
        
        asyncio.create_task(auto_decline())
        
    except Exception as e:
        logger.error(f"Challenge error: {e}")
        await update.message.reply_text(f"❌ Error creating challenge! {str(e)}")

# ============ CHALLENGE RESPONSE HANDLER ============

@private_only
async def handle_challenge_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    chat_id = query.message.chat_id
    
    data = query.data
    
    if data.startswith('accept_'):
        action = 'accept'
        challenge_id = data.replace('accept_', '')
    elif data.startswith('decline_'):
        action = 'decline'
        challenge_id = data.replace('decline_', '')
    else:
        await query.answer("❌ Invalid action!")
        return
    
    challenge = game_manager.get_pending_challenge(challenge_id)
    
    if not challenge:
        await query.answer("❌ Challenge not found or already expired!")
        await query.edit_message_text("❌ Challenge not found or already expired!")
        return
    
    if challenge['challenged_id'] != user_id:
        await query.answer("🚫 You are not the challenged player! Only the challenged player can accept.", show_alert=True)
        return
    
    await query.answer()
    
    if action == "accept":
        result = game_manager.accept_challenge(challenge_id, user_id, chat_id)
        
        if 'error' in result:
            currency = challenge.get('currency', 'INR')
            bet_amount = challenge['bet_amount']
            min_balance = bet_amount * 100
            update_wallet(challenge['challenger_id'], min_balance, currency)
            update_wallet(challenge['challenged_id'], min_balance, currency)
            await query.edit_message_text(f"❌ {result['error']}")
            return
        
        p1 = get_user_profile(challenge['challenger_id'])
        p2 = get_user_profile(challenge['challenged_id'])
        p1_name = p1['username'] if p1 else f"Player{challenge['challenger_id']}"
        p2_name = p2['username'] if p2 else f"Player{challenge['challenged_id']}"
        
        symbol = '₹' if challenge.get('currency', 'INR') == 'INR' else '$'
        game_id = result['game_id']
        bet_amount = challenge['bet_amount']
        
        await query.edit_message_text(
            f"""
{get_brand_header()}

✅ **CHALLENGE ACCEPTED!**

🎲 **PVP Dice Game Starting!**

👤 {p1_name} vs 👤 {p2_name}
💰 Each Player Bet: {symbol}{bet_amount}
💰 Total Pot: {symbol}{bet_amount * 2}
📋 Rounds: {challenge.get('rounds_type', '3R1W').upper()} ({challenge.get('rolls', 3)} rolls each)

🔄 **{p1_name}'s turn to roll!**

Click the ROLL button below:
            """
        )
        
        roll_button = [[InlineKeyboardButton("🎲 ROLL DICE NOW!", callback_data=f"pvp_roll_{game_id}")]]
        roll_markup = InlineKeyboardMarkup(roll_button)
        
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"""
{get_brand_header()}

🎲 @{p1_name}, it's your turn to roll!

Click the button below to roll the animated dice:
            """,
            reply_markup=roll_markup
        )
        
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"""
{get_brand_header()}

⏳ @{p2_name}, please wait for @{p1_name} to roll.

You'll get your turn after they finish.
            """
        )
        
    elif action == "decline":
        currency = challenge.get('currency', 'INR')
        bet_amount = challenge['bet_amount']
        min_balance = bet_amount * 100
        
        update_wallet(challenge['challenger_id'], min_balance, currency)
        update_wallet(challenge['challenged_id'], min_balance, currency)
        
        game_manager.decline_challenge(challenge_id, user_id)
        
        await query.edit_message_text(
            f"""
{get_brand_header()}

❌ **Challenge Declined**

@{challenge.get('challenged_username', 'unknown')} declined the challenge.

💰 Funds have been refunded to both players.
            """
        )

# ============ PVP ROLL ============

@private_only
async def pvp_roll_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    data = query.data
    chat_id = query.message.chat_id
    
    game_id = data.replace('pvp_roll_', '')
    
    pvp_game = pvp_handler.get_game(game_id)
    if not pvp_game:
        await query.edit_message_text("❌ Game not found or already ended!")
        return
    
    if pvp_game['current_turn'] != user_id:
        current_name = pvp_handler.get_current_player_name(pvp_game)
        await query.answer(f"🚫 Not your turn! It's {current_name}'s turn.", show_alert=True)
        return
    
    if not pvp_handler.is_allowed_to_roll(game_id, user_id):
        current_name = pvp_handler.get_current_player_name(pvp_game)
        await query.answer(f"🚫 You are not allowed to roll! It's {current_name}'s turn.", show_alert=True)
        return
    
    if pvp_game['game_over']:
        await query.edit_message_text("❌ Game has already ended!")
        return
    
    if pvp_game.get('roll_in_progress', False):
        await query.answer("⏳ Roll in progress! Please wait...", show_alert=True)
        return
    
    if user_id == pvp_game['challenger_id']:
        if pvp_game['player1_roll_count'] >= pvp_game['total_rolls']:
            await query.edit_message_text("❌ You have already completed all your rolls!")
            return
    else:
        if pvp_game['player2_roll_count'] >= pvp_game['total_rolls']:
            await query.edit_message_text("❌ You have already completed all your rolls!")
            return
    
    await query.edit_message_text("🎲 Rolling animated dice... Please wait!", reply_markup=None)
    
    result = await pvp_handler.make_roll(game_id, user_id, context.bot, chat_id)
    
    if 'error' in result:
        roll_button = [[InlineKeyboardButton("🎲 ROLL DICE NOW!", callback_data=f"pvp_roll_{game_id}")]]
        roll_markup = InlineKeyboardMarkup(roll_button)
        await query.edit_message_text(f"❌ {result['error']}", reply_markup=roll_markup)
        return
    
    if result.get('game_over') and result.get('result'):
        game_result = result['result']
        
        winner_id = game_result.get('winner_id')
        loser_id = game_result.get('loser_id')
        bet_amount = pvp_game['bet_amount']
        currency = pvp_game['currency']
        platform_fee = game_result.get('platform_fee', 0)
        winner_amount = game_result.get('winner_amount', 0)
        total_pot = game_result.get('total_pot', bet_amount * 2)
        winner_name = game_result.get('winner_name', 'Unknown')
        loser_name = game_result.get('loser_name', 'Unknown')
        
        if winner_id:
            winner_prize = winner_amount * 100
            update_wallet(winner_id, winner_prize, currency)
            
            if loser_id:
                winner_balance = get_user_balance(winner_id, currency) / 100
                loser_balance = get_user_balance(loser_id, currency) / 100
                
                # IMPORTANT: Update stats for both players
                update_user_stats(winner_id, won=True, bet_amount=bet_amount, currency=currency, game_type='dice')
                update_user_stats(loser_id, won=False, bet_amount=bet_amount, currency=currency, game_type='dice')
                
                add_transaction(winner_id, 'pvp_win', winner_prize, currency, winner_balance, f"PVP Dice win - {pvp_game['rounds_type']}")
                
                platform_amount = platform_fee * 100
                admin_profile = get_user_profile(ADMIN_USER_ID)
                if admin_profile:
                    admin_currency = admin_profile['currency']
                    update_wallet(ADMIN_USER_ID, platform_amount, admin_currency)
                    admin_balance = get_user_balance(ADMIN_USER_ID, admin_currency)
                    add_transaction(ADMIN_USER_ID, 'platform_fee', platform_amount, admin_currency, admin_balance, f"Platform fee from PVP game")
                
                save_game_history({
                    'game_id': game_id,
                    'game_type': 'dice',
                    'rounds_type': pvp_game['rounds_type'],
                    'player1_id': pvp_game['challenger_id'],
                    'player2_id': pvp_game['challenged_id'],
                    'winner_id': winner_id,
                    'bet_amount': bet_amount,
                    'currency': currency,
                    'platform_fee': platform_fee,
                    'commission_fee': 0,
                    'winner_amount': winner_amount,
                    'player1_rolls': ','.join(map(str, game_result['player1_rolls'])),
                    'player2_rolls': ','.join(map(str, game_result['player2_rolls'])),
                    'player1_total': game_result['player1_total'],
                    'player2_total': game_result['player2_total']
                })
                
                symbol = '₹' if currency == 'INR' else '$'
                
                winner_msg = f"""
{get_brand_header()}

🏆 **GAME OVER!**

🎉 **{winner_name} WINS!** 🎉

📊 **Final Scores:**
👤 {winner_name}: **{game_result['player1_total'] if winner_id == pvp_game['challenger_id'] else game_result['player2_total']}**
👤 {loser_name}: **{game_result['player2_total'] if winner_id == pvp_game['challenger_id'] else game_result['player1_total']}**

💰 **Each Player Bet:** {symbol}{bet_amount}
💰 **Total Pot:** {symbol}{total_pot}
🏆 **Winner Gets:** {symbol}{winner_amount}
📌 **{loser_name} Gets:** {symbol}0

💰 **Updated Balances:**
👤 {winner_name}: {symbol}{winner_balance:.2f} ✅ (+{symbol}{winner_amount})
👤 {loser_name}: {symbol}{loser_balance:.2f} ❌ (-{symbol}{bet_amount})

💡 Start a new game with /start
                """
                
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=winner_msg
                )
                
        elif game_result.get('is_draw'):
            bet_amount_paise = bet_amount * 100
            update_wallet(pvp_game['challenger_id'], bet_amount_paise, currency)
            update_wallet(pvp_game['challenged_id'], bet_amount_paise, currency)
            
            update_user_stats(pvp_game['challenger_id'], draw=True, bet_amount=0, currency=currency, game_type='dice')
            update_user_stats(pvp_game['challenged_id'], draw=True, bet_amount=0, currency=currency, game_type='dice')
            
            save_game_history({
                'game_id': game_id,
                'game_type': 'dice',
                'rounds_type': pvp_game['rounds_type'],
                'player1_id': pvp_game['challenger_id'],
                'player2_id': pvp_game['challenged_id'],
                'winner_id': None,
                'bet_amount': bet_amount,
                'currency': currency,
                'platform_fee': 0,
                'commission_fee': 0,
                'winner_amount': 0,
                'player1_rolls': ','.join(map(str, game_result['player1_rolls'])),
                'player2_rolls': ','.join(map(str, game_result['player2_rolls'])),
                'player1_total': game_result['player1_total'],
                'player2_total': game_result['player2_total']
            })
            
            p1_name = pvp_game.get('challenger_name', 'Player 1')
            p2_name = pvp_game.get('challenged_name', 'Player 2')
            
            p1_balance = get_user_balance(pvp_game['challenger_id'], currency) / 100
            p2_balance = get_user_balance(pvp_game['challenged_id'], currency) / 100
            symbol = '₹' if currency == 'INR' else '$'
            
            draw_msg = f"""
{get_brand_header()}

🤝 **DRAW!**

Both players tied!

👤 {p1_name}: **{game_result['player1_total']}**
👤 {p2_name}: **{game_result['player2_total']}**

💰 Both players get their money back!

💰 **Updated Balances:**
👤 {p1_name}: {symbol}{p1_balance:.2f}
👤 {p2_name}: {symbol}{p2_balance:.2f}

💡 Start a new game with /start
            """
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=draw_msg
            )
        
        pvp_handler.end_game(game_id)
        game_manager.end_game(game_id)
        return
    
    if result.get('switch_turn') and result.get('next_player_id'):
        next_id = result['next_player_id']
        next_name = result['next_player_name']
        
        await query.edit_message_text(result['message'])
        
        roll_button = [[InlineKeyboardButton("🎲 ROLL DICE NOW!", callback_data=f"pvp_roll_{game_id}")]]
        roll_markup = InlineKeyboardMarkup(roll_button)
        
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"""
{get_brand_header()}

🎲 @{next_name}, it's your turn to roll!

Click the button below to roll the animated dice:
            """,
            reply_markup=roll_markup
        )
    else:
        roll_button = [[InlineKeyboardButton("🎲 ROLL AGAIN", callback_data=f"pvp_roll_{game_id}")]]
        roll_markup = InlineKeyboardMarkup(roll_button)
        await query.edit_message_text(result['message'], reply_markup=roll_markup)

# ============ OTHER COMMANDS ============

@private_only
async def balance_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    currency = get_user_currency(user_id)
    symbol = '₹' if currency == 'INR' else '$'
    balance = get_user_balance(user_id, currency) / 100
    
    keyboard = [
        [InlineKeyboardButton("💳 Deposit", callback_data="payment_menu")],
        [InlineKeyboardButton("📤 Withdraw", callback_data="withdraw_main")],
        [InlineKeyboardButton("🔙 Back to Main", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"""
{get_brand_header()}

💰 **BALANCE**

👤 @{update.effective_user.username or 'User'}
💱 Currency: {currency}
💰 Balance: {symbol}{balance:.2f}

📌 Deposit: /deposit
📌 Withdraw: /withdraw
        """,
        reply_markup=reply_markup
    )

@private_only
async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    currency = get_user_currency(user.id)
    symbol = '₹' if currency == 'INR' else '$'
    balance = get_user_balance(user.id, currency) / 100
    
    await update.message.reply_text(
        f"""
{get_brand_header()}

💰 **Your Balance**

Wallet: {symbol}{balance:.2f}
Currency: {currency}

Use /deposit to add funds
Use /withdraw to cash out
        """
    )

@private_only
async def deposit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"""
{get_brand_header()}

💳 **DEPOSIT FUNDS**

Click the button below to go to the payment bot:

@{BOT_USERNAME}

📌 **Payment Limits:**
🇮🇳 INR: ₹100 - ₹5,000
🇺🇸 USD: $0.10 - $20

🔗 Click below to deposit!
        """,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 Go to Payment Bot", url=PAYMENT_BOT_LINK)]
        ])
    )

@private_only
async def withdraw_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("💳 Go to Payment Bot", url=PAYMENT_BOT_LINK)],
        [InlineKeyboardButton("🔙 Back to Main", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"""
{get_brand_header()}

📤 **WITHDRAW FUNDS**

Click the button below to go to the payment bot:

**@{BOT_USERNAME}**

📌 **Withdrawal Limits:**
🇮🇳 INR: ₹100 - ₹5,000
🇺🇸 USD: $0.10 - $20

🔗 Click below to withdraw!
        """,
        reply_markup=reply_markup
    )

@private_only
async def payment_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("💳 Go to Payment Bot", url=PAYMENT_BOT_LINK)],
        [InlineKeyboardButton("🔙 Back to Main", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"""
{get_brand_header()}

💳 **PAYMENT CENTER**

Click the button below to go to the payment bot:

**@{BOT_USERNAME}**

📌 **Payment Features:**
• 💰 Deposit Funds
• 📤 Withdraw Funds
• 📊 Transaction History
• 🔄 Change Currency

**Payment Limits:**
🇮🇳 **INR:**
• Min Deposit: ₹100
• Max Deposit: ₹5,000
• Min Withdraw: ₹100
• Max Withdraw: ₹5,000

🇺🇸 **USD:**
• Min Deposit: $0.10
• Max Deposit: $20
• Min Withdraw: $0.10
• Max Withdraw: $20

🔗 Click below to manage your payments!
        """,
        reply_markup=reply_markup
    )

@private_only
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        message = query.message
        edit_mode = True
    else:
        message = update.message
        edit_mode = False
    
    help_text = f"""
{get_brand_header()}

📚 **COMMANDS LIST**

🎮 **Game Commands:**
/start - Open main menu
/play - Game selection menu
/profile - View your profile
/help - Show this help
/challenge @username - Challenge a player
/roll - Roll dice (in active game)
/balance or /bal - Check your balance
/stats - View your statistics
/history - View game history
/top - View top players

💰 **Wallet Commands:**
/claim - Claim daily bonus
/tip @username amount - Tip another player
/deposit or /depo - Deposit funds
/withdraw or /wd - Withdraw funds

📌 **How to Play:**
1. Click "Challenge Player" or use /challenge
2. Select bet amount
3. Select rounds (2R1W, 3R1W, 4R1W, 5R1W)
4. Challenge a player with /challenge @username
5. Player accepts the challenge
6. Click "ROLL DICE NOW!" to roll
7. Highest total wins!

🎲 **Rounds Explained:**
• 2R1W - 2 rolls, highest total wins
• 3R1W - 3 rolls, highest total wins
• 4R1W - 4 rolls, highest total wins
• 5R1W - 5 rolls, highest total wins

💡 **Tips:**
• Claim daily bonus for free money
• Play bot games to practice
• Check stats to track progress

📊 **Stats Tracked:**
• Games played
• Wins/Losses/Draws
• Win streak
• Rating & Level

💳 **Payment Limits:**
🇮🇳 INR: Min ₹100 | Max ₹5,000
🇺🇸 USD: Min $0.10 | Max $20

👑 Need help? Contact: {ADMIN_USERNAME}
    """
    
    keyboard = [[InlineKeyboardButton("🔙 Back to Main", callback_data="back_to_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if edit_mode:
        await message.edit_text(help_text, reply_markup=reply_markup)
    else:
        await message.reply_text(help_text, reply_markup=reply_markup)

@private_only
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        profile = get_user_profile(user_id)
        
        if not profile:
            await query.edit_message_text("❌ Profile not found!")
            return
        
        win_rate = (profile['total_wins'] / profile['total_games'] * 100) if profile['total_games'] > 0 else 0
        currency = profile['currency']
        symbol = '₹' if currency == 'INR' else '$'
        balance = get_user_balance(user_id, currency) / 100
        
        total_won = profile.get('total_won_inr', 0) if currency == 'INR' else profile.get('total_won_usd', 0)
        total_lost = profile.get('total_lost_inr', 0) if currency == 'INR' else profile.get('total_lost_usd', 0)
        total_won_display = total_won / 100 if total_won else 0
        total_lost_display = total_lost / 100 if total_lost else 0
        net = total_won_display - total_lost_display
        
        level = profile['level']
        experience = profile['experience']
        progress = get_level_progress(experience)
        
        stats_text = f"""
{get_brand_header()}

📊 YOUR STATISTICS

🎮 Games: {profile['total_games']}
🏆 Wins: {profile['total_wins']}
❌ Losses: {profile['total_losses']}
🤝 Draws: {profile['total_draws']}
📈 Win Rate: {win_rate:.1f}%

🔥 Win Streak: {profile.get('win_streak', 0)}
🏆 Best Streak: {profile.get('max_win_streak', 0)}

💰 Wallet: {symbol}{balance:.2f}
📈 Total Won: {symbol}{total_won_display:.2f}
📉 Total Lost: {symbol}{total_lost_display:.2f}
📊 Net Profit: {symbol}{net:.2f}

⭐ Rating: {profile['rating']}
📊 Level: {level}
💡 XP: {experience} ({progress}% to next level)

📅 Member Since: {profile['created_at'][:10] if profile['created_at'] else 'N/A'}

💡 Keep playing to level up!
        """
        
        keyboard = [[InlineKeyboardButton("🔙 Back to Main", callback_data="back_to_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(stats_text, reply_markup=reply_markup)
        return
    
    profile = get_user_profile(user_id)
    
    if not profile:
        await update.message.reply_text("❌ Profile not found!")
        return
    
    win_rate = (profile['total_wins'] / profile['total_games'] * 100) if profile['total_games'] > 0 else 0
    currency = profile['currency']
    symbol = '₹' if currency == 'INR' else '$'
    balance = get_user_balance(user_id, currency) / 100
    
    total_won = profile.get('total_won_inr', 0) if currency == 'INR' else profile.get('total_won_usd', 0)
    total_lost = profile.get('total_lost_inr', 0) if currency == 'INR' else profile.get('total_lost_usd', 0)
    total_won_display = total_won / 100 if total_won else 0
    total_lost_display = total_lost / 100 if total_lost else 0
    net = total_won_display - total_lost_display
    
    level = profile['level']
    experience = profile['experience']
    progress = get_level_progress(experience)
    
    stats_text = f"""
{get_brand_header()}

📊 YOUR STATISTICS

🎮 Games: {profile['total_games']}
🏆 Wins: {profile['total_wins']}
❌ Losses: {profile['total_losses']}
🤝 Draws: {profile['total_draws']}
📈 Win Rate: {win_rate:.1f}%

🔥 Win Streak: {profile.get('win_streak', 0)}
🏆 Best Streak: {profile.get('max_win_streak', 0)}

💰 Wallet: {symbol}{balance:.2f}
📈 Total Won: {symbol}{total_won_display:.2f}
📉 Total Lost: {symbol}{total_lost_display:.2f}
📊 Net Profit: {symbol}{net:.2f}

⭐ Rating: {profile['rating']}
📊 Level: {level}
💡 XP: {experience} ({progress}% to next level)

📅 Member Since: {profile['created_at'][:10] if profile['created_at'] else 'N/A'}

💡 Keep playing to level up!
    """
    
    await update.message.reply_text(stats_text)

@private_only
async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    page = 1
    if context.args:
        try:
            page = int(context.args[0])
        except ValueError:
            page = 1
    
    per_page = 5
    offset = (page - 1) * per_page
    
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        total_games = get_total_history_count(user_id)
        games = get_game_history(user_id, per_page, offset)
        
        if not games:
            await query.edit_message_text(
                f"""
{get_brand_header()}

📜 **No History Found**

You haven't played any PVP games yet.
Start a game with /start → Challenge Player
                """
            )
            return
        
        text = f"""
{get_brand_header()}

📜 **GAME HISTORY - Page {page}/{max(1, (total_games + per_page - 1) // per_page)}**

"""
        for idx, game in enumerate(games, 1 + offset):
            symbol = '₹' if len(game) > 9 and game[9] == 'INR' else '$' if len(game) > 9 else '₹'
            winner = game[7] if len(game) > 7 else None
            is_winner = winner == user_id
            
            if is_winner and winner:
                status = "🏆 WON"
            elif winner:
                status = "❌ LOST"
            else:
                status = "🤝 DRAW"
            
            rounds = game[4] if len(game) > 4 else '3R1W'
            bet = game[8] if len(game) > 8 else 0
            date = game[17][:10] if len(game) > 17 else 'N/A'
            time = game[17][11:16] if len(game) > 17 else 'N/A'
            
            p1_profile = get_user_profile(game[5]) if len(game) > 5 else None
            p2_profile = get_user_profile(game[6]) if len(game) > 6 else None
            p1_name = p1_profile['username'] if p1_profile else f"Player{game[5]}"
            p2_name = p2_profile['username'] if p2_profile else f"Player{game[6]}"
            
            text += f"""
#{idx} {status}
🎲 {rounds.upper()}
💰 Bet: {symbol}{bet}
👤 {p1_name} vs 👤 {p2_name}
📅 {date} {time}
"""
            if len(text) > 4000:
                break
        
        keyboard = []
        nav_row = []
        total_pages = max(1, (total_games + per_page - 1) // per_page)
        
        if page > 1:
            nav_row.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"history_page_{page-1}"))
        if page < total_pages:
            nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"history_page_{page+1}"))
        
        if nav_row:
            keyboard.append(nav_row)
        
        keyboard.append([InlineKeyboardButton("🔙 Back to Main", callback_data="back_to_main")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup)
        return
    
    total_games = get_total_history_count(user_id)
    games = get_game_history(user_id, per_page, offset)
    
    if not games:
        await update.message.reply_text(
            f"""
{get_brand_header()}

📜 **No History Found**

You haven't played any PVP games yet.
Start a game with /start → Challenge Player
            """
        )
        return
    
    text = f"""
{get_brand_header()}

📜 **GAME HISTORY - Page {page}/{max(1, (total_games + per_page - 1) // per_page)}**

"""
    for idx, game in enumerate(games, 1 + offset):
        symbol = '₹' if len(game) > 9 and game[9] == 'INR' else '$' if len(game) > 9 else '₹'
        winner = game[7] if len(game) > 7 else None
        is_winner = winner == user_id
        
        if is_winner and winner:
            status = "🏆 WON"
        elif winner:
            status = "❌ LOST"
        else:
            status = "🤝 DRAW"
        
        rounds = game[4] if len(game) > 4 else '3R1W'
        bet = game[8] if len(game) > 8 else 0
        date = game[17][:10] if len(game) > 17 else 'N/A'
        time = game[17][11:16] if len(game) > 17 else 'N/A'
        
        p1_profile = get_user_profile(game[5]) if len(game) > 5 else None
        p2_profile = get_user_profile(game[6]) if len(game) > 6 else None
        p1_name = p1_profile['username'] if p1_profile else f"Player{game[5]}"
        p2_name = p2_profile['username'] if p2_profile else f"Player{game[6]}"
        
        text += f"""
#{idx} {status}
🎲 {rounds.upper()}
💰 Bet: {symbol}{bet}
👤 {p1_name} vs 👤 {p2_name}
📅 {date} {time}
"""
        if len(text) > 4000:
            break
    
    total_pages = max(1, (total_games + per_page - 1) // per_page)
    text += f"\n📌 Use /history {page+1} for next page" if page < total_pages else ""
    text += f"\n📌 Use /history {page-1} for previous page" if page > 1 else ""
    
    await update.message.reply_text(text)

@private_only
async def history_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    page = int(query.data.replace('history_page_', ''))
    context.args = [str(page)]
    
    await history_command(update, context)

@private_only
async def history_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.args = ['1']
    await history_command(update, context)

@private_only
async def claim_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    success, message = db_claim_daily_bonus(user.id)
    
    if success:
        bonus_info = get_daily_bonus_info(user.id)
        progress = "🟢" * (bonus_info['streak'] % 3) + "⚪" * (3 - (bonus_info['streak'] % 3))
        await update.message.reply_text(
            f"""
{get_brand_header()}

✅ {message}

🔥 Streak: {bonus_info['streak']} days
{progress}

🎉 Come back tomorrow!
            """
        )
    else:
        await update.message.reply_text(
            f"""
{get_brand_header()}

⏳ {message}

📌 Already claimed today!
Come back tomorrow.
            """
        )

@private_only
async def daily_bonus_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    bonus_info = get_daily_bonus_info(user_id)
    
    keyboard = [
        [InlineKeyboardButton("🎁 Claim Bonus", callback_data="claim_daily_bonus")],
        [InlineKeyboardButton("🔙 Back to Main", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    status_text = "✅ Available Now!" if bonus_info['can_claim'] else "⏳ Check tomorrow"
    
    progress = "🟢" * (bonus_info['streak'] % 3) + "⚪" * (3 - (bonus_info['streak'] % 3))
    
    streak = bonus_info['streak']
    if streak >= 10:
        next_target = "🎉 10 Days Streak Achieved!"
    elif streak >= 3:
        next_target = f"🎯 {10 - streak} more days for ₹15"
    else:
        next_target = f"🎯 {3 - streak} more days for ₹10"
    
    await query.edit_message_text(
        f"""
{get_brand_header()}

💰 DAILY BONUS

🔥 Streak: {bonus_info['streak']} days
📈 Status: {status_text}
🎯 Next: {next_target}

{progress}

📌 Rules:
• Claim daily to build streak
• 3 Days Streak = ₹10 Bonus 🎉
• 10 Days Streak = ₹15 Bonus 🎉
• Miss a day = Reset to Day 1

💡 Tip: Login daily!
        """,
        reply_markup=reply_markup
    )

@private_only
async def claim_daily_bonus_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    success, message = db_claim_daily_bonus(user_id)
    
    keyboard = [[InlineKeyboardButton("🔙 Back to Main", callback_data="back_to_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if success:
        bonus_info = get_daily_bonus_info(user_id)
        progress = "🟢" * (bonus_info['streak'] % 3) + "⚪" * (3 - (bonus_info['streak'] % 3))
        
        await query.edit_message_text(
            f"""
{get_brand_header()}

✅ {message}

🔥 Streak: {bonus_info['streak']} days
{progress}

🎉 Come back tomorrow!
            """,
            reply_markup=reply_markup
        )
    else:
        await query.edit_message_text(
            f"""
{get_brand_header()}

⏳ {message}

📌 Already claimed today!
Come back tomorrow.
            """,
            reply_markup=reply_markup
        )

@private_only
async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    await start(update, context)

@private_only
async def noop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()

@private_only
async def set_currency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    currency = query.data.replace('currency_', '')
    user_id = update.effective_user.id
    
    set_user_currency(user_id, currency)
    
    await query.edit_message_text(f"✅ Currency set to {currency}!")
    await start(update, context)

# ============ ADMIN PANEL ============

@private_only
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await query.edit_message_text("❌ Unauthorized!")
        return
    
    keyboard = [
        [InlineKeyboardButton("💰 Add Balance", callback_data="admin_add_balance")],
        [InlineKeyboardButton("💵 Give All ₹10", callback_data="admin_give_all")],
        [InlineKeyboardButton("📊 All Users", callback_data="admin_users")],
        [InlineKeyboardButton("🔙 Back to Main", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"""
{get_brand_header()}

👑 ADMIN PANEL

Welcome {ADMIN_USERNAME}!

Select an option:
        """,
        reply_markup=reply_markup
    )

@private_only
async def admin_add_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await query.edit_message_text("❌ Unauthorized!")
        return
    
    await query.edit_message_text(
        f"""
{get_brand_header()}

💰 ADD BALANCE

Usage: /addbalance @username amount
Example: /addbalance @john 100

Amount is in user's currency (INR or USD)
        """
    )

@private_only
async def admin_addbalance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Unauthorized!")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /addbalance @username amount")
        return
    
    username = context.args[0].replace('@', '')
    try:
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Invalid amount!")
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
    symbol = '₹' if currency == 'INR' else '$'
    
    amount_in_paise = amount * 100
    update_wallet(target_id, amount_in_paise, currency)
    
    balance = get_user_balance(target_id, currency)
    add_transaction(target_id, 'admin_add', amount_in_paise, currency, balance, f"Admin added {symbol}{amount}")
    
    conn.commit()
    conn.close()
    
    await update.message.reply_text(f"✅ Added {symbol}{amount} to @{username}!")
    
    await context.bot.send_message(
        chat_id=target_id,
        text=f"{get_brand_header()}\n\n✅ {symbol}{amount} added to your wallet by admin!"
    )

@private_only
async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await query.edit_message_text("❌ Unauthorized!")
        return
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT user_id, username, first_name, currency, wallet_balance_inr, wallet_balance_usd, total_games, total_wins, level FROM users ORDER BY total_wins DESC LIMIT 20')
    users = c.fetchall()
    conn.close()
    
    if not users:
        await query.edit_message_text("📊 No users found.")
        return
    
    text = f"""
{get_brand_header()}

📊 TOP PLAYERS
"""
    
    for idx, u in enumerate(users, 1):
        symbol = '₹' if u[3] == 'INR' else '$'
        balance = u[4] if u[3] == 'INR' else u[5]
        text += f"""
{idx}. @{u[1] or u[2]}
🆔 {u[0]}
💰 {symbol}{balance/100:.2f}
🏆 {u[7]} wins | Level {u[8]}
"""
    
    keyboard = [[InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup)

@private_only
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

@private_only
async def tip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("❌ Usage: /tip @username amount")
        return
    
    username = context.args[0].replace('@', '')
    try:
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Invalid amount!")
        return
    
    sender_id = update.effective_user.id
    
    try:
        target = None
        try:
            target = await context.bot.get_user_by_username(username)
        except:
            pass
        
        if not target:
            conn = get_db()
            c = conn.cursor()
            c.execute('SELECT user_id FROM users WHERE username = ?', (username,))
            result = c.fetchone()
            conn.close()
            if result:
                try:
                    target = await context.bot.get_chat(result[0])
                except:
                    pass
        
        if not target:
            await update.message.reply_text(f"❌ User @{username} not found.")
            return
        
        currency = get_user_currency(sender_id)
        sender_balance = get_user_balance(sender_id, currency)
        
        if sender_balance < amount * 100:
            symbol = '₹' if currency == 'INR' else '$'
            await update.message.reply_text(f"❌ Insufficient balance! You have {symbol}{sender_balance/100:.2f}")
            return
        
        update_wallet(sender_id, -(amount * 100), currency)
        balance = get_user_balance(sender_id, currency)
        add_transaction(sender_id, 'tip_sent', -(amount * 100), currency, balance, f"Tip sent to @{username}")
        
        target_currency = get_user_currency(target.id)
        update_wallet(target.id, amount * 100, target_currency)
        balance2 = get_user_balance(target.id, target_currency)
        add_transaction(target.id, 'tip_received', amount * 100, target_currency, balance2, f"Tip received from @{update.effective_user.username}")
        
        symbol = '₹' if currency == 'INR' else '$'
        await update.message.reply_text(f"✅ Tipped {symbol}{amount} to @{username}!")
        
        await context.bot.send_message(
            chat_id=target.id,
            text=f"{get_brand_header()}\n\n💝 You received {symbol}{amount} from @{update.effective_user.username}!"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

@private_only
async def roll_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    pvp_game = pvp_handler.get_user_game(user_id)
    if pvp_game and pvp_game['is_active'] and not pvp_game['game_over']:
        if pvp_game['current_turn'] == user_id:
            roll_button = [[InlineKeyboardButton("🎲 ROLL DICE NOW!", callback_data=f"pvp_roll_{pvp_game['game_id']}")]]
            roll_markup = InlineKeyboardMarkup(roll_button)
            
            await update.message.reply_text(
                f"""
{get_brand_header()}

🎲 **Click the button below to roll!**
                """,
                reply_markup=roll_markup
            )
        else:
            current_name = pvp_handler.get_current_player_name(pvp_game)
            await update.message.reply_text(
                f"""
{get_brand_header()}

⏳ **Waiting for {current_name} to roll...**

Please wait for your turn.
                """
            )
        return
    
    game_id = game_manager.get_user_game(user_id)
    if not game_id:
        await update.message.reply_text("❌ No active game! Start one with /start")
        return
    
    result = game_manager.make_move(game_id, user_id)
    
    if 'error' in result:
        await update.message.reply_text(f"❌ {result['error']}")
        return
    
    await update.message.reply_text(result['message'])

# ============ SET COMMANDS ============

async def set_commands(app):
    commands = [
        BotCommand("start", "Open main menu"),
        BotCommand("play", "Game selection menu"),
        BotCommand("profile", "View your profile"),
        BotCommand("help", "Show all commands"),
        BotCommand("challenge", "Challenge a player @username"),
        BotCommand("roll", "Roll dice in active game"),
        BotCommand("balance", "Check your balance"),
        BotCommand("bal", "Check your balance (shortcut)"),
        BotCommand("history", "View game history"),
        BotCommand("top", "View top players"),
        BotCommand("claim", "Claim daily bonus"),
        BotCommand("tip", "Tip another player @username amount"),
        BotCommand("deposit", "Deposit funds"),
        BotCommand("depo", "Deposit funds (shortcut)"),
        BotCommand("withdraw", "Withdraw funds"),
        BotCommand("wd", "Withdraw funds (shortcut)"),
        BotCommand("stats", "View your statistics"),
    ]
    await app.bot.set_my_commands(commands)

# ============ MAIN ============

async def main():
    # Initialize enhanced database
    init_db_enhanced()
    
    request = HTTPXRequest(
        connection_pool_size=8,
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=30.0,
        http_version="1.1"
    )
    
    # Use Application.builder() with async
    app = Application.builder().token(BOT_TOKEN).request(request).build()
    
    app.post_init = set_commands
    
    # ============ COMMANDS ============
    
    # Game Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("play", play_command))
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("challenge", challenge_command))
    app.add_handler(CommandHandler("roll", roll_command))
    app.add_handler(CommandHandler("balance", balance_command))
    app.add_handler(CommandHandler("bal", balance_command))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CommandHandler("top", top_players_menu))
    app.add_handler(CommandHandler("claim", claim_command))
    app.add_handler(CommandHandler("tip", tip_command))
    app.add_handler(CommandHandler("stats", stats_command))
    
    # Payment Redirect Commands (these just redirect to the payment bot)
    app.add_handler(CommandHandler("deposit", deposit_command))
    app.add_handler(CommandHandler("depo", deposit_command))
    
    # Admin Commands
    app.add_handler(CommandHandler("addbalance", admin_addbalance))
    
    # ============ CALLBACKS ============
    
    # Currency
    app.add_handler(CallbackQueryHandler(set_currency, pattern="^currency_"))
    
    # Challenge Flow
    app.add_handler(CallbackQueryHandler(challenge_step1, pattern="^challenge_step1$"))
    app.add_handler(CallbackQueryHandler(challenge_bet_selected, pattern="^challenge_bet_"))
    app.add_handler(CallbackQueryHandler(challenge_rounds_selected, pattern="^challenge_rounds_"))
    app.add_handler(CallbackQueryHandler(handle_challenge_response, pattern="^(accept|decline)_"))
    app.add_handler(CallbackQueryHandler(pvp_roll_button, pattern="^pvp_roll_"))
    
    # Game Menu
    app.add_handler(CallbackQueryHandler(bot_menu, pattern="^bot_menu$"))
    app.add_handler(CallbackQueryHandler(start_game, pattern="^game_type_"))
    app.add_handler(CallbackQueryHandler(play_command, pattern="^play$"))
    
    # Payment Redirect
    app.add_handler(CallbackQueryHandler(payment_menu, pattern="^payment_menu$"))
    app.add_handler(CallbackQueryHandler(withdraw_main, pattern="^withdraw_main$"))
    
    # Daily Bonus
    app.add_handler(CallbackQueryHandler(daily_bonus_menu, pattern="^daily_bonus_menu$"))
    app.add_handler(CallbackQueryHandler(claim_daily_bonus_handler, pattern="^claim_daily_bonus$"))
    
    # History
    app.add_handler(CallbackQueryHandler(history_menu, pattern="^history$"))
    app.add_handler(CallbackQueryHandler(history_page_callback, pattern="^history_page_"))
    
    # Top Players
    app.add_handler(CallbackQueryHandler(top_players_menu, pattern="^top_players_menu$"))
    app.add_handler(CallbackQueryHandler(top_activity, pattern="^top_activity$"))
    
    # Help & Navigation
    app.add_handler(CallbackQueryHandler(help_command, pattern="^help$"))
    app.add_handler(CallbackQueryHandler(back_to_main, pattern="^back_to_main$"))
    app.add_handler(CallbackQueryHandler(noop, pattern="^noop$"))
    
    # Profile & Settings
    app.add_handler(CallbackQueryHandler(profile_command, pattern="^profile$"))
    app.add_handler(CallbackQueryHandler(badges_command, pattern="^badges$"))
    app.add_handler(CallbackQueryHandler(settings_command, pattern="^settings$"))
    app.add_handler(CallbackQueryHandler(settings_currency, pattern="^settings_currency$"))
    app.add_handler(CallbackQueryHandler(balance_callback, pattern="^balance$"))
    
    # Admin Callbacks
    app.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
    app.add_handler(CallbackQueryHandler(admin_add_balance, pattern="^admin_add_balance$"))
    app.add_handler(CallbackQueryHandler(admin_give_all, pattern="^admin_give_all$"))
    app.add_handler(CallbackQueryHandler(admin_users, pattern="^admin_users$"))
    
    # Message handler for custom bet
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, challenge_custom_bet_handler))
    
    print(f"{BRAND_NAME} - Enhanced Game Bot is starting...")
    print(f"👑 Admin: {ADMIN_USERNAME}")
    print(f"💳 Payment Bot: {PAYMENT_BOT_LINK}")
    print("📌 Using shared database: payment_bot.db")
    print("✅ Enhanced features loaded:")
    print("  • Simplified Profile with Badges")
    print("  • 12-Level System with correct emojis")
    print("  • Activity Points System with correct wallet amounts")
    print("  • Top Activity Leaderboard with wallet balances")
    print("  • Badges System")
    print("  • Settings Menu")
    print("  • /play command for game selection")
    print("  • Custom bet amount fixed and working")
    print("  • 🔒 PRIVATE CHAT ONLY MODE ENABLED")
    print("  • Bot only responds in private chats")
    print("  • WAGER SYSTEM COMPLETELY REMOVED")
    print("  • Python 3.13+ compatible")
    print("✅ Bot is running!")
    
    # Run the bot with async
    await app.run_polling()
