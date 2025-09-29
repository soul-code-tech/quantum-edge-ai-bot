# check_bingx_render.py
import ccxt
import sys

exchange = ccxt.bingx({'options': {'defaultType': 'swap'}, 'enableRateLimit': True})
try:
    exchange.load_markets()
    swaps = [s for s in exchange.markets.keys() if s.endswith('-USDT') and exchange.markets[s].get('active')]
    print("Доступные свопы на BingX (Render):")
    for s in sorted(swaps):
        print(s)
except Exception as e:
    print("Ошибка загрузки рынков:", e)
    sys.exit(1)
