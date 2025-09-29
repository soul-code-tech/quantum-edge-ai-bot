# order_logger.py
import logging
import os
from datetime import datetime

logger = logging.getLogger("orders")
logger.setLevel(logging.INFO)

# Лог в /tmp (единственное доступное место)
log_path = "/tmp/orders.log"
handler = logging.FileHandler(log_path)
formatter = logging.Formatter('%(asctime)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

def log_order(symbol, side, amount, limit_price, stop_price, tp_price, order_id):
    msg = f"{symbol} | {side} | amount={amount:.6f} | entry={limit_price:.2f} | SL={stop_price:.2f} | TP={tp_price:.2f} | id={order_id}"
    logger.info(msg)
    print(f"📝 ORDER LOGGED: {msg}")
