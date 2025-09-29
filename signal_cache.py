# signal_cache.py
import hashlib
import time
import logging
from datetime import datetime, timedelta

logger = logging.getLogger("signal_cache")

COOLDOWN_SECONDS = 3600   # 1 час

def signal_hash(df):
    """Хэш последнего бара»"""
    last_row = df.iloc[-1][['open', 'high', 'low', 'close', 'volume']]
    return hashlib.md5(last_row.to_json().encode()).hexdigest()

def is_fresh_signal(symbol: str, df):
    from main import last_signal_time, last_signal_hash
    h = signal_hash(df)
    t = time.time()
    if (t - last_signal_time.get(symbol, 0)) < COOLDOWN_SECONDS:
        return False
    if last_signal_hash.get(symbol) == h:
        return False
    last_signal_hash[symbol] = h
    last_signal_time[symbol] = t
    return True
