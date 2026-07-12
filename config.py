import os
from dotenv import load_dotenv

load_dotenv()

# Bot Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN', '8828883232:AAHm3XnCehecaRG_2CsGZKDsa96RTuDZG20')
BOT_USERNAME = os.getenv('BOT_USERNAME', 'CasinoIndia2026_bot')

# ========== DATABASE ==========
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///pvp_bot.db')

# ========== ADMIN SETTINGS ==========
ADMIN_USER_ID = 5943318266  # Your Telegram User ID
ADMIN_USERNAME = "@XTOP_879"

# ========== UPI PAYMENT SETTINGS ==========
UPI_ID = "praveennnnguru@fam"  # Your UPI ID
UPI_NAME = "Praveen Kumar"
BANK_NAME = "State Bank of India"
ACCOUNT_NUMBER = "1234567890"
IFSC_CODE = "SBIN0001234"

# ========== CRYPTO SETTINGS ==========
CRYPTO_ADDRESSES = {
    'BTC': '1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa',
    'ETH': '0x742d35Cc6634C0532925a3b844Bc454e4438f44e',
    'USDT': '0x742d35Cc6634C0532925a3b844Bc454e4438f44e'
}

# ========== CURRENCY SETTINGS ==========
CURRENCY_OPTIONS = ['INR', 'USD']
DEFAULT_CURRENCY = 'INR'
USD_TO_INR = 83

# ========== BETTING SETTINGS ==========
BET_AMOUNTS_INR = [50, 100, 200, 500, 1000, 2000, 5000]
BET_AMOUNTS_USD = [1, 2, 5, 10, 20, 50, 100]

PLATFORM_COMMISSION_PERCENT = 20
WINNER_GETS_PERCENT = 80
STARTING_WALLET_BALANCE_INR = 100
STARTING_WALLET_BALANCE_USD = 1

# ========== DICE GAME SETTINGS ==========
DICE_ROLL_OPTIONS = [2, 3, 4]
DEFAULT_ROLLS = 3

# Daily Rewards
DAILY_BONUS_INR = 50
DAILY_BONUS_USD = 1

# Game Entry Fees (in coins)
GAME_FEES = {
    'dice': 10,
    'bowling': 20,
    'basketball': 15,
    'mines': 25,
    'throwball': 20
}

# Payment Settings
MIN_DEPOSIT_INR = 10
MAX_DEPOSIT_INR = 100000
MIN_DEPOSIT_USD = 1
MAX_DEPOSIT_USD = 2000

MIN_WITHDRAW_INR = 100
MAX_WITHDRAW_INR = 10000
MIN_WITHDRAW_USD = 2
MAX_WITHDRAW_USD = 200

# Emojis
EMOJIS = {
    'coins': '🪙',
    'trophy': '🏆',
    'star': '⭐',
    'game': '🎮',
    'dice': '🎲',
    'bowling': '🎳',
    'basketball': '🏀',
    'mines': '💣',
    'throwball': '🎯',
    'pvp': '⚔️',
    'bot': '🤖',
    'solo': '👤',
    'refresh': '🔄',
    'tip': '💝',
    'payment': '💳',
    'daily': '💰',
    'stats': '📊',
    'help': '❓',
    'money': '💵',
    'winner': '🏆',
    'usd': '💲',
    'inr': '₹',
    'deposit': '📥',
    'withdraw': '📤',
    'history': '📋',
    'success': '✅',
    'failed': '❌',
    'pending': '⏳',
    'approved': '✔️',
    'rejected': '❌',
    'completed': '🎉',
    'bank': '🏦',
    'crypto': '🪙',
    'upi': '📱'
}