# main.py
from flask import Flask
import threading
import time
import os
import requests
import logging
from data_fetcher import get_bars
from strategy import calculate_strategy_signals
from trader import BingXTrader
from lstm_model import LSTMPredictor
from trainer import initial_train_all, sequential_trainer, load_model, train_one
from download_weights import download_weights

logging.basicConfig(
    filename="bot.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("bot")

app = Flask(__name__)

SYMBOLS = [
    'BTC-USDT', 'ETH-USDT', 'SOL-USDT', 'BNB-USDT',
    'XRP-USDT', 'DOGE-USDT', 'TON-USDT', 'AVAX-USDT',
    'SHIB-USDT', 'LINK-USDT'
]

RISK_PERCENT = 1.0
STOP_LOSS_PCT = 1.5
TAKE_PROFIT_PCT = 3.0
LSTM_CONFIDENCE = 0.67
TIMEFRAME = '1h'
LOOKBACK = 200
SIGNAL_COOLDOWN = 3600
UPDATE_TRAILING_INTERVAL = 300

lstm_models = {}
traders = {}
last_signal_time = {}
last_trailing_update = {}
total_trades = 0


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
    global total_trades
    while True:
        try:
            current_time = time.time()
            for symbol in SYMBOLS:
                if not lstm_models[symbol].is_trained:
                    logger.info(f"{symbol} не обучен – пропуск.")
                    continue

                df = get_bars(symbol, TIMEFRAME, LOOKBACK)
                if df is None or len(df) < 100:
                    logger.warning(f"{symbol}: мало данных – пропуск.")
                    continue
                df = calculate_strategy_signals(df, 60)
                buy_signal = df['buy_signal'].iloc[-1]
                sell_signal = df['sell_signal'].iloc[-1]
                long_score = df['long_score'].iloc[-1]
                short_score = df['short_score'].iloc[-1]

                if current_time - last_signal_time.get(symbol, 0) < SIGNAL_COOLDOWN:
                    continue

                prob = lstm_models[symbol].predict_next(df)
                if prob < LSTM_CONFIDENCE:
                    continue

                strong = (buy_signal and long_score >= 5) or (sell_signal and short_score >= 5)
                if not strong:
                    continue

                side = 'buy' if buy_signal else 'sell'
                atr = df['atr'].iloc[-1]
                risk_amount = 100 * RISK_PERCENT / 100
                amount = max(risk_amount / (atr * 1.5), 0.001)

                order = traders[symbol].place_order(side=side, amount=amount,
                                                  stop_loss_percent=STOP_LOSS_PCT,
                                                  take_profit_percent=TAKE_PROFIT_PCT)
                if order:
                    total_trades += 1
                    last_signal_time[symbol] = current_time
                    logger.info(f"📈 СДЕЛКА {side} {symbol}")

            if time.time() - last_trailing_update.get('global', 0) > UPDATE_TRAILING_INTERVAL:
                for s in SYMBOLS:
                    traders[s].update_trailing_stop()
                last_trailing_update['global'] = time.time()

            time.sleep(60)
        except Exception as e:
            logger.error(f"Критическая ошибка: {e}")
            time.sleep(60)


def start_all():
    logger.info("Скачиваем веса...")
    download_weights()

    logger.info("Загружаем модели...")
    to_train = []
    for s in SYMBOLS:
        model = load_model(s)
        if model:
            lstm_models[s] = model
            traders[s] = BingXTrader(symbol=s, use_demo=True, leverage=10)
        else:
            lstm_models[s] = LSTMPredictor()
            traders[s] = BingXTrader(symbol=s, use_demo=True, leverage=10)
            to_train.append(s)

    if to_train:
        logger.info(f"К обучению: {len(to_train)} пар")
        initial_train_all(to_train, epochs=5)
        for s in to_train:
            lstm_models[s] = load_model(s) or LSTMPredictor()

    logger.info("Запуск фонового дообучения (30 мин)...")
    threading.Thread(target=sequential_trainer, args=(SYMBOLS, 1800, 2), daemon=True).start()

    logger.info("Запуск торговой стратегии...")
    threading.Thread(target=run_strategy, daemon=True).start()

    threading.Thread(target=keep_alive, daemon=True).start()
    logger.info("Бот запущен: обучение + торговля + keep-alive.")


@app.route('/')
def wake_up():
    trained = sum(1 for m in lstm_models.values() if m.is_trained)
    return f"✅ Quantum Edge Bot LIVE! Обучено: {trained}/{len(SYMBOLS)}", 200


@app.route('/health')
def health_check():
    return "OK", 200


if __name__ == "__main__":
    threading.Thread(target=start_all, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
