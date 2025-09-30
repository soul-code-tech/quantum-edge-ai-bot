# src/data_fetcher.py
import ccxt
import pandas as pd

def get_bars(symbol, timeframe="1h", limit=500):
    try:
        ex = ccxt.bingx({'enableRateLimit': True})
        ohlcv = ex.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp','open','high','low','close','volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        return df
    except:
        return None

def get_funding_rate(symbol):
    try:
        ex = ccxt.bingx()
        funding = ex.fetch_funding_rate(symbol)
        return funding['fundingRate'] * 100  # в %
    except:
        return 0.0
