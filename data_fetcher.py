# data_fetcher.py
import ccxt
import pandas as pd

def get_bars(symbol='BTC-USDT', timeframe='1h', limit=100):
    exchange = ccxt.bingx({
        'options': {'defaultType': 'swap'},
        'enableRateLimit': True,
        # ✅ ВАЖНО: УБРАТЬ ВСЕ ПОПЫТКИ ИСПОЛЬЗОВАТЬ vst — ОНИ ЛОМАЮТСЯ!
    })
    
    # ✅ ИСПОЛЬЗУЕМ ОБЫЧНЫЙ ДОМЕН — НЕ vst!
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df
