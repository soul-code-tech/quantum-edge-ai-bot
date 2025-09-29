# signal_cache.py
import hashlib
import time
import logging
from datetime import datetime, timedelta

logger = logging.getLogger("signal_cache")

COOLDOWN_SECONDS = 3600   # 1 час

# Храним в памяти (Render не сохраняет на диск)
_LAST_SIGNAL_TIME = {}
_LAST_SIGNAL_HASH = {}

def signal_hash(df):
    """Хэш последнего бара"""
    last_row = df.iloc[-1][['open', 'high', 'low', 'close', 'volume']]
    return hashlib.md5(last_row.to_json().encode()).hexdigest()

def is_fresh_signal(symbol: str, df):
    h = signal_hash(df)
    t = time.time()
    if (t - _LAST_SIGNAL_TIME.get(symbol, 0)) < COOLDOWN_SECONDS:
        return False
    if _LAST_SIGNAL_HASH.get(symbol) == h:
        return False
    _LAST_SIGNAL_HASH[symbol] = h
    _LAST_SIGNAL_TIME[symbol] = t
    return True
