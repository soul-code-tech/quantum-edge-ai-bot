# position_monitor.py
import threading
import time
import logging
import ccxt

logger = logging.getLogger("position_monitor")

def start_position_monitor(traders, symbols):
    def monitor():
        while True:
            for sym in symbols:
                trader = traders.get(sym)
                if not trader or not trader.position:
                    continue
                try:
                    ticker = trader.exchange.fetch_ticker(sym)
                    current = float(ticker['last'])
                    side = trader.position['side']
                    entry = trader.position['entry']
                    trailing = trader.trailing_stop_price or entry * (1 - 0.01 if side == 'buy' else 1 + 0.01)

                    # трейлинг-стоп
                    if side == 'buy' and current > entry * 1.005:
                        new_stop = current * 0.99
                        if new_stop > trailing:
                            trader.update_trailing_stop(new_stop)
                            logger.info(f"📈 {sym}: trailing raised to {new_stop:.2f}")

                except Exception as e:
                    logger.error(f"monitor {sym}: {e}")
            time.sleep(30)

    threading.Thread(target=monitor, daemon=True).start()
    logger.info("✅ Position monitor started")
