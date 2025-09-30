# main.py
import os
import threading
import logging
import time
import ccxt
from flask import Flask

from trainer import load_model
from data_fetcher import get_bars, get_funding_rate
from strategy import calculate_strategy_signals, get_market_regime
from risk_manager import calculate_position_size, calculate_stop_loss, calculate_take_profit

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
logger = logging.getLogger("main")

SYMBOLS = [
    "BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT",
    "XRP/USDT:USDT", "DOGE/USDT:USDT", "AVAX/USDT:USDT", "SHIB/USDT:USDT",
    "LINK/USDT:USDT", "PENGU/USDT:USDT"
]

models = {}
# active_positions: {symbol: {'order_id': str, 'size': float, 'side': str, 'created': timestamp}}
active_positions = {}
app = Flask(__name__)

# Singleton exchange
_exchange = None

def get_exchange():
    global _exchange
    if _exchange is None:
        _exchange = ccxt.bingx({
            'apiKey': os.getenv('BINGX_API_KEY'),
            'secret': os.getenv('BINGX_SECRET_KEY'),
            'options': {'defaultType': 'swap'},
            'enableRateLimit': True
        })
    return _exchange

def get_account_balance():
    try:
        ex = get_exchange()
        balance = ex.fetch_balance()
        return balance['USDT']['free']
    except Exception as e:
        logger.error(f"Ошибка получения баланса: {e}")
        return 1000.0  # fallback

def place_order_with_sl_tp(symbol, side, amount, price):
    try:
        ex = get_exchange()
        sl = calculate_stop_loss(get_bars(symbol, "1h", 100), side)
        tp = calculate_take_profit(get_bars(symbol, "1h", 100), side)

        params = {
            'postOnly': True,
            'stopLoss': {'type': 'stop', 'price': sl},
            'takeProfit': {'type': 'take_profit', 'price': tp}
        }

        order = ex.create_order(symbol, 'limit', side, amount, price, params)
        logger.info(f"✅ Ордер {side.upper()} {symbol} | {amount:.6f} по {price:.2f} | SL={sl:.2f}, TP={tp:.2f}")
        return order
    except Exception as e:
        logger.error(f"❌ Ошибка ордера {symbol}: {e}")
        return None

def monitor_order(symbol, order_id, timeout=120):
    """Ожидает исполнения ордера или таймаута."""
    ex = get_exchange()
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            order = ex.fetch_order(order_id, symbol)
            if order['status'] == 'closed':
                filled = order['filled']
                logger.info(f"✅ Ордер {order_id} исполнен на {filled:.6f}")
                return filled
            time.sleep(5)
        except Exception as e:
            logger.warning(f"⚠️ Ошибка мониторинга {order_id}: {e}")
            time.sleep(10)
    logger.warning(f"⏰ Таймаут ордера {order_id} для {symbol}")
    try:
        ex.cancel_order(order_id, symbol)
        logger.info(f"🚫 Ордер {order_id} отменён")
    except:
        pass
    return 0.0

def trade_loop():
    max_positions = int(os.getenv('MAX_POSITIONS', '5'))
    min_vol = float(os.getenv('MIN_VOLATILITY', '0.005'))
    
    while True:
        account_balance = get_account_balance()
        logger.info(f"💼 Баланс: {account_balance:.2f} USDT")

        for symbol in SYMBOLS:
            if len(active_positions) >= max_positions:
                break
            if symbol in active_positions:
                continue

            try:
                model = models.get(symbol)
                if not model or not model.is_trained:
                    continue

                df = get_bars(symbol, "1h", 200)
                if df is None or len(df) < 100:
                    continue

                df = calculate_strategy_signals(df, 60)
                regime = get_market_regime(df)
                funding = get_funding_rate(symbol)
                volatility = df['volatility'].iloc[-1] if 'volatility' in df else 0.0

                if regime != 'trending_up' or volatility < min_vol:
                    continue

                prob = model.predict_proba(df)
                long_score = df['long_score'].iloc[-1]
                trend_score = df['trend_score'].iloc[-1]

                side = None
                if (long_score >= 5 and trend_score >= 3 and 
                    prob > 0.75 and funding < 0.05):
                    side = 'buy'
                elif (long_score <= 2 and trend_score <= 1 and 
                      prob < 0.25 and funding > -0.05):
                    side = 'sell'

                if side:
                    size = calculate_position_size(df, risk_pct=1.0, account_balance=account_balance)
                    current_price = df['close'].iloc[-1]
                    limit_price = current_price * (0.9995 if side == 'buy' else 1.0005)

                    if size <= 0:
                        continue

                    order = place_order_with_sl_tp(symbol, side, size, limit_price)
                    if order:
                        active_positions[symbol] = {
                            'order_id': order['id'],
                            'side': side,
                            'size': 0.0,
                            'created': time.time()
                        }
                        filled = monitor_order(symbol, order['id'])
                        if filled > 0:
                            active_positions[symbol]['size'] = filled
                            logger.info(f"📊 Позиция {symbol} открыта: {filled:.6f} @ {limit_price:.2f}")
                        else:
                            active_positions.pop(symbol, None)

            except Exception as e:
                logger.error(f"Ошибка торговли {symbol}: {e}")

        time.sleep(60)

@app.route("/health")
def health():
    return {"status": "ok"}

def initialize_models():
    for s in SYMBOLS:
        model = load_model(s)
        if model:
            models[s] = model
            logger.info(f"✅ Модель {s} загружена")
        else:
            logger.warning(f"⚠️ Модель {s} не найдена")

if __name__ == "__main__":
    logger.info("✅ Quantum Edge AI Bot (ДЕМО-ТОРГОВЛЯ)")
    logger.info("🛡️ Режим: BingX Demo, post-only limit + SL/TP")
    logger.info("📈 Торговля: только в тренде, funding-фильтр, макс. 5 позиций")

    initialize_models()
    threading.Thread(target=trade_loop, daemon=True).start()

    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
