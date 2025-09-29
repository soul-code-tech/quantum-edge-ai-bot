# signal_cache.py
import time

_SIGNAL_CACHE = {}
_COOLDOWN = 3600  # 1 час

def is_fresh_signal(symbol: str, df) -> bool:
    last_time = _SIGNAL_CACHE.get(symbol, 0)
    current_time = time.time()
    if current_time - last_time < _COOLDOWN:
        return False
    _SIGNAL_CACHE[symbol] = current_time
    return True
