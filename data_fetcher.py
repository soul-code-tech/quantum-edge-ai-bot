# data_fetcher.py
import ccxt
import pandas as pd
import time
import random

def fetch_with_retry(func, max_retries=3, delay=2, backoff=1.5):
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise e
            wait_time = delay * (backoff ** attempt) + random.uniform(0, 1)
            print(f"⚠️ Ошибка при вызове {func.__name__}: {e}. Повтор через {wait_time:.1f} сек. (попытка {attempt + 1}/{max_retries})")
            time.sleep(wait_time)

def get_bars(symbol='BTC-USDT', timeframe='1h', limit=100):
    base_urls = [
        'https://open-api.bingx.com',
        'https://open-api.bingx.io'
    ]
    
    for base_url in base_urls:
        try:
            exchange = ccxt.bingx({
                'options': {'defaultType': 'swap', 'baseUrl': base_url},
                'enableRateLimit': True,
            })
            ohlcv = fetch_with_retry(lambda: exchange.fetch_ohlcv(symbol, timeframe, limit=limit))
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except Exception as e:
            print(f"⚠️ Не удалось подключиться к {base_url}: {e}")
            continue

    raise Exception("❌ Все домены BingX недоступны")
