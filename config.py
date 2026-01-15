import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Telegram Bot
    TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
    
    # Tradier API
    TRADIER_TOKEN = os.getenv('TRADIER_TOKEN')
    TRADIER_ACCOUNT_ID = os.getenv('TRADIER_ACCOUNT_ID')
    TRADIER_API_URL = "https://api.tradier.com/v1/"
    
    # Trading Parameters
    RISK_REWARD_RATIO = 2.0
    MAX_RISK_PERCENT = 1.0
    DEFAULT_EXPIRY_DAYS = 7
    SESSION_TIMES = {
        'asian_start': 20,  # 8 PM EST
        'asian_end': 2,     # 2 AM EST
        'london_start': 3,  # 3 AM EST
        'london_end': 7,    # 7 AM EST
        'ny_start': 8,      # 8 AM EST
        'ny_end': 12        # 12 PM EST
    }
    
    # Emojis
    EMOJI = {
        'bull': '🐂',
        'bear': '🐻',
        'neutral': '⚖️',
        'up': '📈',
        'down': '📉',
        'fire': '🔥',
        'rocket': '🚀',
        'warning': '⚠️',
        'check': '✅',
        'cross': '❌',
        'money': '💰',
        'chart': '📊',
        'clock': '⏰',
        'calendar': '📅'
    }
