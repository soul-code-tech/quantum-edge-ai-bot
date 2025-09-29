# data_fetcher.py
import ccxt
import pandas as pd
import logging

logger = logging.getLogger("data_fetcher")

def get_bars(symbol='BTC-USDT', timeframe='1h', limit=500):
    exchange = ccxt.bingx({
        'options': {'defaultType': 'swap'},
        'enableRateLimit': True,
    })
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def get_funding_rate(symbol='BTC-USDT') -> float:
    try:
        exchange = ccxt.bingx({'options': {'defaultType': 'swap'}})
        fr = exchange.fetch_funding_rate(symbol)
        rate = fr.get('fundingRate')
        return float(rate) if rate is not None else 0.0
    except Exception as e:
        logger.warning(f"funding-rate {symbol}: {e} (ставим 0.0)")
        return 0.0
