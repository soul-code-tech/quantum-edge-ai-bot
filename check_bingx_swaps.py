# check_bingx_swaps.py
import ccxt
exchange = ccxt.bingx({'options': {'defaultType': 'swap'}})
exchange.load_markets()
swaps = [s for s in exchange.markets.keys() if s.endswith('-USDT') and exchange.markets[s].get('type') == 'swap']
print("Доступные свопы на BingX:")
for s in sorted(swaps):
    print(s)
