import ccxt
import pandas as pd
import time
import random

def fetch_with_retry(func, max_retries=3, delay=2, backoff=1.5):
    """Умный retry для API-запросов BingX"""
    base_urls = [
        'https://open-api.bingx.com',      # ✅ УБРАНЫ ПРОБЕЛЫ!
        'https://open-api.bingx.io'       # ✅ УБРАНЫ ПРОБЕЛЫ!
    ]
    
    for attempt in range(max_retries):
        for base_url in base_urls:
            try:
                exchange = ccxt.bingx({
                    'options': {'defaultType': 'swap', 'baseUrl': base_url},
                    'enableRateLimit': True,
                    'headers': {'User-Agent': 'QuantumEdgeAI-Bot/1.0'}
                })
                result = func(exchange)
                return result
            except Exception as e:
                if attempt == max_retries - 1 and base_url == base_urls[-1]:
                    raise Exception(f"❌ Все домены и попытки исчерпаны: {e}")
                wait_time = delay * (backoff ** attempt) + random.uniform(0, 1)
                print(f"⚠️ Ошибка при обращении к {base_url}: {e}. Повтор через {wait_time:.1f} сек. (попытка {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
                break

def get_bars(symbol='BTC-USDT', timeframe='1h', limit=50):
    """Получает OHLCV-данные с биржи с защитой от сбоев"""
    def fetch_ohlcv(exchange):
        return exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    
    ohlcv = fetch_with_retry(fetch_ohlcv)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df
