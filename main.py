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
from risk_manager import calculate_position_size

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
logger = logging.getLogger("main")

SYMBOLS = [
    "BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT",
    "XRP/USDT:USDT", "DOGE/USDT:USDT", "AVAX/USDT:USDT", "SHIB/USDT:USDT",
    "LINK/USDT:USDT", "PENGU/USDT:USDT"
]

models = {}
active_positions = set()
app = Flask(__name__)

def get_exchange():
    return ccxt.bingx({
        'apiKey': os.getenv('BINGX_API_KEY'),
        'secret': os.getenv('BINGX_SECRET_KEY'),
        'options': {'defaultType': 'swap'},
        'enableRateLimit': True
    })

def place_order(symbol, side, amount, price):
    try:
        ex = get_exchange()
        order = ex.create_order(
            symbol=symbol,
            type='limit',
            side=side,
            amount=amount,
            price=price,
            params={'postOnly': True}
        )
        logger.info(f"✅ {side.upper()} {symbol} | {amount:.6f} по {price:.2f} (post-only)")
        active_positions.add(symbol)
        return order
    except Exception as e:
        logger.error(f"❌ Ошибка ордера {symbol}: {e}")
        return None

def trade_loop():
    max_positions = int(os.getenv('MAX_POSITIONS', '5'))
    min_vol = float(os.getenv('MIN_VOLATILITY', '0.005'))
    
    while True:
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

                # LONG
                if (long_score >= 5 and trend_score >= 3 and 
                    prob > 0.75 and funding < 0.05):

                    size = calculate_position_size(df, risk_pct=1.0, account_balance=1000)
                    current_price = df['close'].iloc[-1]
                    limit_price = current_price * 0.9995
                    if size > 0:
                        place_order(symbol, 'buy', size, limit_price)

                # SHORT (опционально)
                elif (long_score <= 2 and trend_score <= 1 and 
                      prob < 0.25 and funding > -0.05):

                    size = calculate_position_size(df, risk_pct=1.0, account_balance=1000)
                    current_price = df['close'].iloc[-1]
                    limit_price = current_price * 1.0005
                    if size > 0:
                        place_order(symbol, 'sell', size, limit_price)

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
    logger.info("🛡️ Режим: BingX Demo (VST), post-only limit")
    logger.info("📈 Торговля: только в тренде, funding-фильтр, макс. 5 позиций")

    initialize_models()
    threading.Thread(target=trade_loop, daemon=True).start()

    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
