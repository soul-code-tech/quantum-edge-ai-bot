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

# ---------- Telegram ----------
TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT = os.getenv("TG_CHAT")

# ---------- trader ----------
SLIP_BUFFER = 0.001  # 0.1%
MIN_LOTS = {
    'BTC-USDT': 0.001,
    'ETH-USDT': 0.001,
    'BNB-USDT': 0.01,
    'SOL-USDT': 0.01,
    'XRP-USDT': 1,
    'ADA-USDT': 1,
    'DOGE-USDT': 1,
    'DOT-USDT': 0.1,
    'MATIC-USDT': 1,
    'LTC-USDT': 0.01
}

# ---------- динамические символы ----------
def get_available_symbols():
    """
    Автоматически получает доступные своп-пары с BingX.
    Если не получается (например, на Render), возвращает fallback.
    """
    try:
        import ccxt
        import logging
        logger = logging.getLogger("config")
        exchange = ccxt.bingx({'options': {'defaultType': 'swap'}, 'enableRateLimit': True})
        exchange.load_markets()
        swaps = [s for s in exchange.markets.keys() if s.endswith('-USDT') and exchange.markets[s].get('type') == 'swap']
        if swaps:
            logger.info(f"🌐 Найдено {len(swaps)} доступных своп-пар: {swaps}")
            return swaps
        else:
            logger.warning("⚠️ Не найдено доступных своп-пар — используем fallback")
            return ['BTC-USDT', 'ETH-USDT']  # fallback
    except Exception as e:
        import logging
        logger = logging.getLogger("config")
        logger.warning(f"⚠️ Ошибка при получении свопов: {e} — используем fallback")
        return ['BTC-USDT', 'ETH-USDT']  # fallback

SYMBOLS = get_available_symbols()
