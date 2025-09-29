# main.py
import os
import sys
import logging
import threading
import time
import requests
from flask import Flask
from data_fetcher import get_bars
from strategy import calculate_strategy_signals
from trader import BingXTrader
from lstm_model import EnsemblePredictor
from trainer import train_one, load_model, download_weights
from position_monitor import start_position_monitor
from signal_cache import is_fresh_signal
from pnl_monitor import PNL_BP, start_pnl_monitor
from config import USE_DEMO, LEVERAGE, RISK_PERCENT, STOP_LOSS_PCT, TAKE_PROFIT_PCT, LSTM_CONFIDENCE, TIMEFRAME, COOLDOWN_SECONDS, UPDATE_TRAILING_INTERVAL, TG_TOKEN, TG_CHAT

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("main")

app = Flask(__name__)
app.register_blueprint(PNL_BP, url_prefix='/pnl')

SYMBOLS = [
    'BTC-USDT', 'ETH-USDT', 'SOL-USDT', 'BNB-USDT',
    'XRP-USDT', 'DOGE-USDT', 'MATIC-USDT', 'LTC-USDT',
    'ADA-USDT', 'LINK-USDT'
]

lstm_models = {}
traders = {}
for s in SYMBOLS:
    lstm_models[s] = EnsemblePredictor()
    traders[s] = BingXTrader(symbol=s, use_demo=USE_DEMO, leverage=LEVERAGE)

def keep_alive():
    host = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
    if not host:
        logger.warning("RENDER_EXTERNAL_HOSTNAME не задан — keep-alive отключён")
        return
    url = f"https://{host}/health"
    logger.info(f"🔁 Keep-alive включён: {url}")
    while True:
        try:
            requests.get(url, timeout=10)
        except Exception as e:
            logger.debug(f"Keep-alive error: {e}")
        time.sleep(120)

def run_strategy():
    while True:
        try:
            for symbol in SYMBOLS:
                if not getattr(lstm_models[symbol], 'is_trained', False):
                    continue

                df = get_bars(symbol, TIMEFRAME, 500)
                if df is None or len(df) < 100:
                    continue

                df = calculate_strategy_signals(df, symbol, 60)

                if not is_fresh_signal(symbol, df):
                    continue

                current_price = df['close'].iloc[-1]
                buy_signal = df['buy_signal'].iloc[-1]
                sell_signal = df['sell_signal'].iloc[-1]
                long_score = df['long_score'].iloc[-1]
                short_score = df['short_score'].iloc[-1]

                model = lstm_models[symbol]
                lstm_prob = model.predict_next(df)
                lstm_confident = lstm_prob > LSTM_CONFIDENCE

                strong_strategy = (buy_signal and long_score >= 5) or (sell_signal and short_score >= 5)
                if strong_strategy and lstm_confident:
                    side = 'buy' if buy_signal else 'sell'
                    atr = df['atr'].iloc[-1]
                    amount = max(0.001, (100 * RISK_PERCENT / 100) / (atr * 1.5))
                    traders[symbol].place_limit_order(
                        side=side,
                        amount=amount,
                        entry=current_price,
                        stop_loss_percent=STOP_LOSS_PCT,
                        take_profit_percent=TAKE_PROFIT_PCT
                    )

            time.sleep(60)
        except Exception as e:
            logger.error(f"Ошибка в стратегии: {e}")
            time.sleep(60)

def start_all():
    logger.info("=== СТАРТ start_all() ===")
    download_weights()
    trained = 0
    for s in SYMBOLS:
        model = load_model(s)
        if model:
            lstm_models[s] = model
            trained += 1
        else:
            logger.warning(f"⚠️ Модель {s} отсутствует — будет обучена")
    if trained == 0:
        logger.info("🧠 Нет готовых моделей — начинаем первичное обучение по одной...")
        for s in SYMBOLS:
            if train_one(s, epochs=5):
                lstm_models[s].is_trained = True
                logger.info(f"✅ {s} обучена — включена в торговлю")
            time.sleep(5)
    else:
        missing = [s for s in SYMBOLS if not getattr(lstm_models[s], 'is_trained', False)]
        for s in missing:
            if train_one(s, epochs=5):
                lstm_models[s].is_trained = True
                logger.info(f"✅ {s} обучена — включена в торговлю")
            time.sleep(5)

    threading.Thread(target=run_strategy, daemon=True).start()
    start_position_monitor(traders, SYMBOLS)
    threading.Thread(target=keep_alive, daemon=True).start()
    start_pnl_monitor()

    logger.info("🚀 Quantum Edge AI Bot полностью запущен!")

@app.route('/')
def wake_up():
    active = sum(1 for m in lstm_models.values() if getattr(m, 'is_trained', False))
    return f"✅ Quantum Edge AI Bot LIVE | Активных моделей: {active}/{len(SYMBOLS)}", 200

@app.route('/health')
def health_check():
    return "OK", 200

if __name__ == "__main__":
    threading.Thread(target=start_all, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
