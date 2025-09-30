# main.py
import os
import threading
import logging
import ccxt
from flask import Flask
from data_fetcher import get_bars
from strategy import calculate_strategy_signals, get_market_regime
from lstm_model import LSTMPredictor
from trainer import load_model

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
logger = logging.getLogger("main")

SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT", ...]  # ваши пары
lstm_models = {}
active_positions = set()

app = Flask(__name__)

@app.route("/health")
def health():
    return {"status": "ok"}

def place_order(symbol, side, amount, price):
    """Разместить post-only limit-ордер."""
    try:
        exchange = ccxt.bingx({
            'apiKey': os.getenv('BINGX_API_KEY'),
            'secret': os.getenv('BINGX_SECRET_KEY'),
            'options': {'defaultType': 'swap'}
        })
        order = exchange.create_order(
            symbol=symbol,
            type='limit',
            side=side,
            amount=amount,
            price=price,
            params={'postOnly': True}  # ← получаем ребейт!
        )
        logger.info(f"✅ Ордер {side} {symbol} на {amount} по {price}")
        active_positions.add(symbol)
        return order
    except Exception as e:
        logger.error(f"❌ Ошибка ордера {symbol}: {e}")

def calculate_position_size(df, risk_pct=1.0, account_balance=1000):
    current_price = df['close'].iloc[-1]
    atr = df['atr'].iloc[-1]
    stop_distance = atr * 1.5  # 1.5 ATR
    risk_amount = account_balance * (risk_pct / 100)
    position_size = risk_amount / stop_distance
    return max(position_size, 0.001)

def trade_with_filter(symbol):
    try:
        df = get_bars(symbol, "1h", 200)
        if df is None or len(df) < 100:
            return

        df = calculate_strategy_signals(df, 60)
        regime = get_market_regime(df)

        # Фильтр режима
        if regime not in ['trending_up', 'trending_down']:
            return

        model = lstm_models.get(symbol)
        if not model or not model.is_trained:
            return

        prob = model.predict_proba(df)
        current_price = df['close'].iloc[-1]

        # LONG
        if (df['long_score'].iloc[-1] >= 5 and 
            df['trend_score'].iloc[-1] >= 3 and 
            regime == 'trending_up' and 
            prob > 0.75):

            size = calculate_position_size(df)
            # Размещаем limit-ордер чуть ниже рынка
            limit_price = current_price * 0.9995
            place_order(symbol, 'buy', size, limit_price)

        # SHORT
        elif (df['long_score'].iloc[-1] <= 2 and 
              df['trend_score'].iloc[-1] <= 1 and 
              regime == 'trending_down' and 
              prob < 0.25):

            size = calculate_position_size(df)
            limit_price = current_price * 1.0005
            place_order(symbol, 'sell', size, limit_price)

    except Exception as e:
        logger.error(f"Ошибка торговли {symbol}: {e}")

def run_trading():
    while True:
        for symbol in SYMBOLS:
            if symbol not in active_positions:  # Не входим в уже открытую позицию
                trade_with_filter(symbol)
        time.sleep(60)

def initialize_models():
    for s in SYMBOLS:
        model = load_model(s, lookback=60)
        if model:
            lstm_models[s] = model
        else:
            lstm_models[s] = LSTMPredictor(lookback=60)

if __name__ == "__main__":
    initialize_models()
    threading.Thread(target=run_trading, daemon=True).start()
    
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
