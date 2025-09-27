# data_fetcher.py — РАБОТАЕТ С BINGX
import ccxt
import pandas as pd

def get_bars(symbol='BTC-USDT', timeframe='1h', limit=50):
    exchange = ccxt.bingx({
        'options': {'defaultType': 'swap'},
        'enableRateLimit': True,
        'headers': {
            'User-Agent': 'QuantumEdgeAI-Bot/1.0'
        }
    })
    symbol_for_api = symbol.replace('-', '/')  # BTC-USDT → BTC/USDT
    ohlcv = exchange.fetch_ohlcv(symbol_for_api, timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df
