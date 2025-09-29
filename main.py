# main.py
import os
import sys
import logging
import threading
import time
import requests
from flask import Flask

# Настройка логгера
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("main")

from data_fetcher import get_bars
from strategy import calculate_strategy_signals
from trader import BingXTrader
from lstm_model import LSTMPredictor
from trainer import train_one, load_model, download_weights
from position_monitor import start_position_monitor
from signal_cache import is_fresh_signal

app = Flask(__name__)

SYMBOLS = [
    'BTC-USDT', 'ETH-USDT', 'SOL-USDT', 'BNB-USDT',
    'XRP-USDT', 'DOGE-USDT', 'TON-USDT', 'AVAX-USDT',
    'SHIB-USDT', 'LINK-USDT'
]

RISK_PERCENT = 1.0
STOP_LOSS_PCT = 1.5
TAKE_PROFIT_PCT = 3.0
LSTM_CONFIDENCE = 0.75
TIMEFRAME = '1h'
LOOKBACK = 500

lstm_models = {}
traders = {}
for s in SYMBOLS:
    lstm_models[s] = LSTMPredictor()
    traders[s] = BingXTrader(symbol=s, use_demo=True, leverage=10)

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
                if not lstm_models[symbol].is_trained:
                    continue

                df = get_bars(symbol, TIMEFRAME, LOOKBACK)
                if df is None or len(df) < 100:
                    continue

                # ✅ ИСПРАВЛЕНО: передаём symbol как второй аргумент
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
                    amount = max(0.001, (100 * 0.01) / (atr * 1.5))
                    traders[symbol].place_order(
                        side=side,
                        amount=amount,
                        stop_loss_percent=STOP_LOSS_PCT,
                        take_profit_percent=TAKE_PROFIT_PCT
                    )

            time.sleep(60)
        except Exception as e:
            logger.error(f"Ошибка в стратегии: {e}")
            time.sleep(60)

def start_all():
    logger.info("=== СТАРТ start_all() ===")
    
    # 1. Скачиваем веса из GitHub
    download_weights()

    # 2. Загружаем существующие модели
    trained_count = 0
    for s in SYMBOLS:
        model = load_model(s)
        if model:
            lstm_models[s] = model
            logger.info(f"✅ Модель {s} загружена из GitHub")
            trained_count += 1
        else:
            logger.warning(f"⚠️ Модель {s} отсутствует — будет обучена")

    # 3. Обучаем недостающие модели ПОСЛЕДОВАТЕЛЬНО
    if trained_count == 0:
        logger.info("🧠 Нет готовых моделей — начинаем первичное обучение по одной...")
        for s in SYMBOLS:
            if train_one(s, epochs=5):
                lstm_models[s].is_trained = True
                logger.info(f"✅ {s} обучена — включена в торговлю")
            time.sleep(5)
    else:
        missing = [s for s in SYMBOLS if not lstm_models[s].is_trained]
        for s in missing:
            if train_one(s, epochs=5):
                lstm_models[s].is_trained = True
                logger.info(f"✅ {s} обучена — включена в торговлю")
            time.sleep(5)

    # 4. Запуск компонентов
    threading.Thread(target=run_strategy, daemon=True).start()
    start_position_monitor(traders, SYMBOLS)
    threading.Thread(target=keep_alive, daemon=True).start()

    # 5. Фоновое дообучение (каждый час, 2 эпохи)
    def hourly_retrain():
        while True:
            logger.info("🔁 Начало цикла дообучения (2 эпохи на пару)...")
            for s in SYMBOLS:
                if lstm_models[s].is_trained:
                    train_one(s, epochs=2)
                time.sleep(10)
            time.sleep(3600)

    threading.Thread(target=hourly_retrain, daemon=True).start()
    logger.info("🚀 Quantum Edge AI Bot полностью запущен!")

@app.route('/')
def wake_up():
    active = sum(1 for m in lstm_models.values() if m.is_trained)
    return f"✅ Quantum Edge AI Bot LIVE | Активных моделей: {active}/{len(SYMBOLS)}", 200

@app.route('/health')
def health_check():
    return "OK", 200

# Подключаем PnL-мониторинг (если файл существует)
try:
    from pnl_monitor import PNL_BP, start_pnl_monitor
    app.register_blueprint(PNL_BP)
    start_pnl_monitor()
except Exception as e:
    logger.warning(f"Не удалось запустить PnL-мониторинг: {e}")

if __name__ == "__main__":
    threading.Thread(target=start_all, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
