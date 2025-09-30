# src/data_fetcher.py
import ccxt
import pandas as pd

def get_bars(symbol: str, timeframe: str = "1h", limit: int = 500):
    """
    Загружает OHLCV данные с BingX.
    """
    try:
        exchange = ccxt.bingx({
            'enableRateLimit': True,
            'options': {'defaultType': 'swap'}
        })
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        if not ohlcv:
            return None
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        return df
    except Exception as e:
        print(f"Ошибка загрузки данных для {symbol}: {e}")
        return None
