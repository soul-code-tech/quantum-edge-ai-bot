# data_fetcher.py
import ccxt
import pandas as pd

def get_bars(symbol: str, timeframe: str = "1h", limit: int = 500):
    try:
        exchange = ccxt.bingx({'enableRateLimit': True})
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        return df
    except Exception as e:
        print(f"Ошибка загрузки данных для {symbol}: {e}")
        return None
