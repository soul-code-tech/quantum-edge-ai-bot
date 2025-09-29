# config.py
import os
from dotenv import load_dotenv

load_dotenv()

# ---------- биржа ----------
USE_DEMO = os.getenv("USE_DEMO", "True").lower() == "true"
LEVERAGE = int(os.getenv("LEVERAGE", "3"))

# ---------- риск ----------
RISK_PERCENT = 1.0
STOP_LOSS_PCT = 1.5
TAKE_PROFIT_PCT = 3.0
LSTM_CONFIDENCE = 0.75

# ---------- тайминги ----------
TIMEFRAME = "1h"
COOLDOWN_SECONDS = 3600
UPDATE_TRAILING_INTERVAL = 300
SLIP_BUFFER = 0.0005          # 0,05 % «подтираем» цену, чтобы 100 % попасть в мейкер

# ---------- Telegram ----------
TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT = os.getenv("TG_CHAT")

# ---------- реальные swap-тикеры BingX (проверены 29.09.2025) ----------
REAL_SWAP_TICKERS = [
    'BTC-USDT', 'ETH-USDT', 'SOL-USDT', 'BNB-USDT', 'XRP-USDT',
    'ADA-USDT', 'DOGE-USDT', 'MATIC-USDT', 'LTC-USDT', 'LINK-USDT'
]
