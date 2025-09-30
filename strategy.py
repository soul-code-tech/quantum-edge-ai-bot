#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quantum Edge AI Bot – DEMO / REAL ready
- пост-онли лимитки + SL/TP сразу
- LONG & SHORT
- фильтры: regime, funding, vol, min-size
- информативные логи
- без внешнего монитора / БД
"""

import os
import time
import threading
import logging
import signal
from datetime import datetime

import ccxt
from flask import Flask

from trainer import load_model
from data_fetcher import get_bars, get_funding_rate
from strategy import calculate_strategy_signals, get_market_regime
from risk_manager import (
    calculate_position_size,
    calculate_stop_loss,
    calculate_take_profit,
)

# -----------------  CONFIG  ------------------
MAX_POS = int(os.getenv("MAX_POSITIONS", "5"))
RISK_PCT = float(os.getenv("RISK_PCT", "1.0"))
MIN_VOL = float(os.getenv("MIN_VOLATILITY", "0.005"))
RR_RATIO = float(os.getenv("RISK_REWARD_RATIO", "2.5"))
ORDER_TO = int(os.getenv("ORDER_TIMEOUT", "120"))
PORT = int(os.getenv("PORT", "10000"))
SYMBOLS = [
    "BTC/USDT:USDT",
    "ETH/USDT:USDT",
    "SOL/USDT:USDT",
    "BNB/USDT:USDT",
    "XRP/USDT:USDT",
    "DOGE/USDT:USDT",
    "AVAX/USDT:USDT",
    "SHIB/USDT:USDT",
    "LINK/USDT:USDT",
    "PENGU/USDT:USDT",
]
# --------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")

models: dict = {}
active_pos: dict = {}  # symbol -> {order_id, side, size, sl, tp, created}

last_df: dict = {}
last_bar_time: dict = {}

_exchange = None
app = Flask(__name__)


# ---------- UTILS ----------
def get_exchange():
    global _exchange
    if _exchange is None:
        _exchange = ccxt.bingx({
            "apiKey": os.getenv("BINGX_API_KEY"),
            "secret": os.getenv("BINGX_SECRET_KEY"),
            "options": {"defaultType": "swap"},
            "enableRateLimit": True,
        })
    return _exchange


def get_balance():
    try:
        return get_exchange().fetch_balance()["USDT"]["free"]
    except Exception as e:
        logger.error(f"Баланс не получен: {e}")
        return 1000.0


def get_cached_bars(symbol, tf="1h", limit=200):
    """Обновляем данные не чаще 1 раза в 60 с."""
    now = time.time()
    if (symbol not in last_bar_time) or (now - last_bar_time[symbol] > 60):
        df = get_bars(symbol, tf, limit)
        if df is not None and len(df) >= 100:
            last_df[symbol] = df
            last_bar_time[symbol] = now
    return last_df.get(symbol)


def human_float(n: float) -> str:
    """Красивое округление для логов."""
    return f"{n:.4f}".rstrip("0").rstrip(".") if n > 0.01 else f"{n:.6f}"


# ---------- ORDER ----------
def place_limit_sl_tp(symbol: str, side: str, amount: float, price: float):
    ex = get_exchange()
    market = ex.market(symbol)
    min_amt = market["limits"]["amount"]["min"]
    if amount < min_amt:
        logger.info(f"⏭️  {symbol} {side}: объём {amount:.6f} < мин {min_amt}")
        return None

    df = get_cached_bars(symbol, "1h", 100)
    if df is None:
        return None

    sl = calculate_stop_loss(df, side)
    tp = calculate_take_profit(df, side, risk_reward_ratio=RR_RATIO)

    params = {
        "postOnly": True,
        "stopLoss": {"type": "stop", "price": sl},
        "takeProfit": {"type": "take_profit", "price": tp},
    }

    try:
        order = ex.create_order(
            symbol=symbol,
            type="limit",
            side=side,
            amount=amount,
            price=price,
            params=params,
        )
        logger.info(
            f"📨 {side.upper()} {symbol} | "
            f"цена={human_float(price)} | "
            f"size={human_float(amount)} | "
            f"SL={human_float(sl)} | "
            f"TP={human_float(tp)}"
        )
        return order
    except Exception as e:
        logger.error(f"❌ Ордер {symbol} {side}: {e}")
        return None


def await_fill(symbol: str, order_id: str, timeout: int = ORDER_TO):
    """Ждём закрытия или таймаута. Возвращаем filled."""
    ex = get_exchange()
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            o = ex.fetch_order(order_id, symbol)
            if o["status"] == "closed":
                filled = float(o["filled"])
                logger.info(f"✅ Исполнено {symbol}: {human_float(filled)} шт")
                return filled
            time.sleep(5)
        except Exception as e:
            logger.warning(f"⚠️  Ожидание {order_id}: {e}")
            time.sleep(5)
    logger.warning(f"⏰ Таймаут {order_id} – отмена")
    try:
        ex.cancel_order(order_id, symbol)
    except:
        pass
    return 0.0


# ---------- CORE ----------
def one_symbol_flow(symbol: str, balance: float):
    """Анализ + вход (long/short) для одного символа."""
    model = models.get(symbol)
    if not model or not model.is_trained:
        return

    df = get_cached_bars(symbol, "1h", 200)
    if df is None or len(df) < 100:
        return

    df = calculate_strategy_signals(df, 60)
    regime = get_market_regime(df)
    funding = get_funding_rate(symbol)
    volatility = df["volatility"].iloc[-1] if "volatility" in df else 0.0
    atr = df["atr"].iloc[-1]

    long_score = int(df["long_score"].iloc[-1])
    trend_score = int(df["trend_score"].iloc[-1])
    prob = float(model.predict_proba(df))

    logger.info(
        f"🔍 {symbol} | "
        f"long={long_score}/5  trend={trend_score}/4  "
        f"prob={prob:.3f}  funding={funding:.3f}%  "
        f"vol={volatility:.4f}  atr={human_float(atr)}  regime={regime}"
    )

    # LONG
    if (
        long_score >= 5
        and trend_score >= 3
        and prob > 0.75
        and funding < 0.05
        and volatility > MIN_VOL
        and regime == "trending_up"
    ):
        logger.info(f"✅ Сигнал LONG {symbol}")
        size = calculate_position_size(df, risk_pct=RISK_PCT, account_balance=balance)
        price = df["close"].iloc[-1] * 0.9995
        if size <= 0:
            logger.info(f"⏭️  {symbol} LONG: size ≤ 0")
            return
        order = place_limit_sl_tp(symbol, "buy", size, price)
        if order:
            filled = await_fill(symbol, order["id"])
            if filled > 0:
                active_pos[symbol] = {"side": "buy", "size": filled, "created": time.time()}
                logger.info(f"📊 Позиция {symbol} LONG открыта: {human_float(filled)}")
            else:
                active_pos.pop(symbol, None)

    # SHORT
    elif (
        long_score <= 2
        and trend_score <= 1
        and prob < 0.25
        and funding > -0.05
        and volatility > MIN_VOL
        and regime == "trending_down"
    ):
        logger.info(f"✅ Сигнал SHORT {symbol}")
        size = calculate_position_size(df, risk_pct=RISK_PCT, account_balance=balance)
        price = df["close"].iloc[-1] * 1.0005
        if size <= 0:
            logger.info(f"⏭️  {symbol} SHORT: size ≤ 0")
            return
        order = place_limit_sl_tp(symbol, "sell", size, price)
        if order:
            filled = await_fill(symbol, order["id"])
            if filled > 0:
                active_pos[symbol] = {"side": "sell", "size": filled, "created": time.time()}
                logger.info(f"📊 Позиция {symbol} SHORT открыта: {human_float(filled)}")
            else:
                active_pos.pop(symbol, None)

    else:
        reasons = []
        if long_score < 5:
            reasons.append("long<5")
        if trend_score < 3:
            reasons.append("trend<3")
        if prob <= 0.75:
            reasons.append("prob≤0.75")
        if funding >= 0.05:
            reasons.append("funding≥0.05")
        if volatility <= MIN_VOL:
            reasons.append(f"vol≤{MIN_VOL:.1%}")
        if regime not in {"trending_up", "trending_down"}:
            reasons.append("flat")
        logger.info(f"⏭️  Пропуск {symbol}: {'; '.join(reasons)}")


def trade_loop():
    while True:
        balance = get_balance()
        logger.info(
            f"💼 Баланс={human_float(balance)} USDT  "
            f"Открыто={len(active_pos)}/{MAX_POS}"
        )

        for symbol in SYMBOLS:
            if len(active_pos) >= MAX_POS:
                break
            if symbol in active_pos:
                continue
            one_symbol_flow(symbol, balance)

        time.sleep(60)


def init_models():
    for s in SYMBOLS:
        if (model := load_model(s)) and model.is_trained:
            models[s] = model
            logger.info(f"✅ Модель {s} загружена")
        else:
            logger.warning(f"⚠️  Модель {s} не найдена / не обучена")


@app.route("/health")
def health():
    return {"status": "ok", "positions": len(active_pos), "balance": get_balance()}


def shutdown(signum, frame):
    logger.info("🛑 SIGTERM/SIGINT — отмена всех ордеров...")
    try:
        get_exchange().cancel_all_orders()
    except:
        pass
    os._exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    logger.info("✅ Quantum Edge AI Bot (DEMO / REAL)")
    logger.info("🛡️  Post-only limit + SL/TP  |  RR=1:%s", int(RR_RATIO))
    logger.info("📊  MAX_POS=%s  RISK=%s%%  MIN_VOL=%s%%", MAX_POS, RISK_PCT, MIN_VOL * 100)

    init_models()
    threading.Thread(target=trade_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT, debug=False)
