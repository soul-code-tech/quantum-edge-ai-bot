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
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

from data_fetcher import get_bars
from strategy import calculate_strategy_signals
from trader import BingXTrader
from lstm_model import LSTMPredictor
from trainer import initial_train_all, sequential_trainer, load_model
from download_weights import download_weights
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
UPDATE_TRAILING_INTERVAL = 300

lstm_models = {}
traders = {}
for s in SYMBOLS:
    lstm_models[s] = LSTMPredictor()
    traders[s] = BingXTrader(symbol=s, use_demo=True, leverage=10)

def keep_alive():
    host = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
    if not host:
        return
    url = f"https://{host}/health"
    while True:
        try:
            requests.get(url, timeout=10)
        except:
            pass
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

                df = calculate_strategy_signals(df, 60)
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
                    amount = max(0.001, (100 * 0.01) / (atr * 1.5))  # простой расчёт
                    traders[symbol].place_order(
                        side=side,
                        amount=amount,
                        stop_loss_percent=STOP_LOSS_PCT,
                        take_profit_percent=TAKE_PROFIT_PCT
                    )

            time.sleep(60)
        except Exception as e:
            logging.error(f"Стратегия упала: {e}")
            time.sleep(60)

def start_all():
    logging.info("=== СТАРТ start_all() ===")
    download_weights()
    
    # Загрузка существующих моделей
    for s in SYMBOLS:
        model = load_model(s)
        if model:
            lstm_models[s] = model
            logging.info(f"✅ Модель {s} загружена")
        else:
            logging.info(f"⏳ Модель {s} не найдена — будет обучена")

    initial_train_all(SYMBOLS, epochs=5)
    threading.Thread(target=sequential_trainer, args=(SYMBOLS, 900, 3), daemon=True).start()
    threading.Thread(target=run_strategy, daemon=True).start()
    start_position_monitor(traders, SYMBOLS)
    threading.Thread(target=keep_alive, daemon=True).start()
    logging.info("🚀 Bot запущен!")

@app.route('/')
def wake_up():
    return f"✅ Quantum Edge AI Bot LIVE on {len(SYMBOLS)} pairs!", 200

@app.route('/health')
def health_check():
    return "OK", 200

if __name__ == "__main__":
    threading.Thread(target=start_all, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
