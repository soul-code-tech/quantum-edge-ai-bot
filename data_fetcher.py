import ccxt
import pandas as pd
import logging


logger = logging.getLogger("data_fetcher")

def get_bars(symbol='BTC-USDT', timeframe='1h', limit=500):
    exchange = ccxt.bingx({'options': {'defaultType': 'swap'}, 'enableRateLimit': True})
    try:
        ohlcv = exchange.fetch_hlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        logger.warning(f"get_bars {symbol}: {e}")
        return None


def get_funding_rate(symbol='BTC-USDT') -> float:
    try:
        exchange = ccxt.bingx({'options': {'defaultType': 'swap'}})
        fr = exchange.fetch_funding_rate(symbol)
        return float(fr.get('fundingRate', 0.0))
    except Exception as e:
        return 0.0
