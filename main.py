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
active_positions = {}
app = Flask(__name__)

_exchange = None
last_df = {}
last_update = {}
last_sync = 0

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
        return 1000.0

def get_cached_bars(symbol, timeframe="1h", limit=200):
    now = time.time()
    if symbol not in last_update or now - last_update[symbol] > 60:
        df = get_bars(symbol, timeframe, limit)
        if df is not None:
            last_df[symbol] = df
            last_update[symbol] = now
    return last_df.get(symbol)

def place_order_with_sl_tp(symbol, side, amount, price):
    try:
        ex = get_exchange()
        market = ex.market(symbol)
        min_amount = market['limits']['amount']['min']
        if amount < min_amount:
            logger.warning(f"🚫 {symbol}: размер {amount:.6f} < минимум {min_amount}")
            return None

        df = get_cached_bars(symbol, "1h", 100)
        if df is None:
            return None

        sl = calculate_stop_loss(df, side)
        rr_ratio = float(os.getenv('RISK_REWARD_RATIO', '2.5'))
        tp = calculate_take_profit(df, side, rr_ratio)

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
    global last_sync
    max_positions = int(os.getenv('MAX_POSITIONS', '5'))
    min_vol = float(os.getenv('MIN_VOLATILITY', '0.005'))

    while True:
        account_balance = get_account_balance()
        logger.info(f"💼 Баланс: {account_balance:.2f} USDT")

        # Синхронизация позиций с биржей каждые 5 минут
        if time.time() - last_sync > 300:
            try:
                ex = get_exchange()
                positions = ex.fetch_positions()
                open_symbols = {p['symbol'] for p in positions if p['contracts'] and float(p['contracts']) > 0}
                for sym in list(active_positions.keys()):
                    if sym not in open_symbols:
                        active_positions.pop(sym, None)
                        logger.info(f"🔒 Позиция {sym} закрыта (внешне)")
                last_sync = time.time()
            except Exception as e:
                logger.error(f"Ошибка синхронизации позиций: {e}")

        for symbol in SYMBOLS:
            if len(active_positions) >= max_positions:
                break
            if symbol in active_positions:
                continue

            try:
                model = models.get(symbol)
                if not model or not model.is_trained:
                    continue

                df = get_cached_bars(symbol, "1h", 200)
                if df is None or len(df) < 100:
                    continue

                df = calculate_strategy_signals(df, 60)
                regime = get_market_regime(df)
                funding = get_funding_rate(symbol)
                volatility = df['volatility'].iloc[-1] if 'volatility' in df else 0.0

                long_score = df['long_score'].iloc[-1]
                trend_score = df['trend_score'].iloc[-1]
                prob = model.predict_proba(df)

                logger.info(
                    f"🔍 {symbol} | "
                    f"long_score={long_score}/5 | "
                    f"trend_score={trend_score}/4 | "
                    f"LSTM_prob={prob:.3f} | "
                    f"funding={funding:.3f}% | "
                    f"volatility={volatility:.4f} | "
                    f"regime={regime}"
                )

                # LONG
                meets_long = (
                    long_score >= 5 and
                    trend_score >= 3 and
                    prob > 0.75 and
                    funding < 0.05 and
                    volatility > min_vol and
                    regime == 'trending_up'
                )

                # SHORT
                short_score = long_score  # или отдельный short_score
                meets_short = (
                    short_score <= 2 and
                    trend_score <= 1 and
                    prob < 0.25 and
                    funding > -0.05 and
                    volatility > min_vol and
                    regime == 'trending_down'
                )

                if meets_long:
                    logger.info(f"✅ ВХОД: LONG {symbol} — все условия выполнены")
                    size = calculate_position_size(df, risk_pct=1.0, account_balance=account_balance)
                    current_price = df['close'].iloc[-1]
                    limit_price = current_price * 0.9995
                    if size <= 0:
                        continue
                    order = place_order_with_sl_tp(symbol, 'buy', size, limit_price)
                    if order:
                        active_positions[symbol] = {
                            'order_id': order['id'],
                            'side': 'buy',
                            'size': 0.0,
                            'created': time.time()
                        }
                        filled = monitor_order(symbol, order['id'])
                        if filled > 0:
                            active_positions[symbol]['size'] = filled
                            logger.info(f"📊 Позиция {symbol} открыта: {filled:.6f} @ {limit_price:.2f}")
                        else:
                            active_positions.pop(symbol, None)

                elif meets_short:
                    logger.info(f"✅ ВХОД: SHORT {symbol} — все условия выполнены")
                    size = calculate_position_size(df, risk_pct=1.0, account_balance=account_balance)
                    current_price = df['close'].iloc[-1]
                    limit_price = current_price * 1.0005
                    if size <= 0:
                        continue
                    order = place_order_with_sl_tp(symbol, 'sell', size, limit_price)
                    if order:
                        active_positions[symbol] = {
                            'order_id': order['id'],
                            'side': 'sell',
                            'size': 0.0,
                            'created': time.time()
                        }
                        filled = monitor_order(symbol, order['id'])
                        if filled > 0:
                            active_positions[symbol]['size'] = filled
                            logger.info(f"📊 Позиция {symbol} открыта: {filled:.6f} @ {limit_price:.2f}")
                        else:
                            active_positions.pop(symbol, None)

                else:
                    reasons = []
                    if long_score < 5: reasons.append("long_score < 5")
                    if trend_score < 3: reasons.append("trend_score < 3")
                    if prob <= 0.75: reasons.append("LSTM_prob ≤ 0.75")
                    if funding >= 0.05: reasons.append("funding ≥ 0.05%")
                    if volatility <= min_vol: reasons.append(f"volatility ≤ {min_vol:.1%}")
                    if regime != 'trending_up': reasons.append("не в тренде")
                    logger.info(f"⏭️ Пропуск {symbol}: {'; '.join(reasons)}")

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
