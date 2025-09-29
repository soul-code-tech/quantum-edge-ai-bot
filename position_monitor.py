# position_monitor.py
import threading
import time
import logging

logger = logging.getLogger("monitor")

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
                    entry = trader.position['entry_price']
                    trailing = trader.trailing_stop_price

                    if side == 'buy' and current > entry * 1.005:
                        new_stop = current * 0.99
                        if new_stop > trailing:
                            trader.update_trailing_stop(new_stop)
                            logger.info(f"📈 {sym}: trailing raised to {new_stop:.2f}")

                    elif side == 'sell' and current < entry * 0.995:
                        new_stop = current * 1.01
                        if new_stop < trailing:
                            trader.update_trailing_stop(new_stop)
                            logger.info(f"📉 {sym}: trailing lowered to {new_stop:.2f}")

                except Exception as e:
                    logger.error(f"monitor {sym}: {e}")
            time.sleep(30)

    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    logger.info("✅ Position monitor started")
