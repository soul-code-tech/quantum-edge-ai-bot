# data_fetcher.py
import ccxt
import pandas as pd
import logging

logger = logging.getLogger("bot")

def get_bars(symbol='BTC-USDT', timeframe='1h', limit=400):
    exchange = ccxt.bingx({
        "options": {"defaultType": "swap"},
        "enableRateLimit": True,
    })
    # оставляем ДЕФИС (BingX использует BTC-USDT, а не BTCUSDT)
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def get_funding_rate(symbol='BTC-USDT') -> float:
    try:
        exchange = ccxt.bingx({"options": {"defaultType": "swap"}})
        fr = exchange.fetch_funding_rate(symbol)
        return float(fr['fundingRate']) * 100   # в процентах
    except Exception as e:
        logger.error(f"funding-rate {symbol}: {e}")
        return 0.0
