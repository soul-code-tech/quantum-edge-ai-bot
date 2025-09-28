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
    sym = symbol.replace("-", "")
    ohlcv = exchange.fetch_ohlcv(sym, timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df


def get_funding_rate(symbol='BTC-USDT') -> float:
    """
    Возвращает последний funding-rate (8ч) в процентах.
    BingX: 0.0005 → 0.05 %
    """
    try:
        exchange = ccxt.bingx({"options": {"defaultType": "swap"}})
        sym = symbol.replace("-", "")
        fr = exchange.fetch_funding_rate(sym)
        return float(fr['fundingRate']) * 100          # в процентах
    except Exception as e:
        logger.error(f"funding-rate {symbol}: {e}")
        return 0.0
