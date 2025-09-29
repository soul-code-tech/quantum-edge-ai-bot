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
from lstm_model import LSTMPredictor
from trainer import train_one, load_model, download_weights, sequential_trainer
from position_monitor import start_position_monitor
from signal_cache import is_fresh_signal
from config import USE_DEMO, LEVERAGE, RISK_PERCENT, STOP_LOSS_PCT, TAKE_PROFIT_PCT, LSTM_CONFIDENCE, TIMEFRAME, COOLDOWN_SECONDS, SYMBOLS

# === Логирование ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("main")

# === Flask ===
app = Flask(__name__)

# === Хранилище ===
lstm_models = {}
traders = {}
for s in SYMBOLS:
    lstm_models[s] = LSTMPredictor()
    traders[s] = BingXTrader(symbol=s, use_demo=USE_DEMO, leverage=LEVERAGE)

# === Роуты ===
@app.route('/')
def wake_up():
    active = sum(1 for m in lstm_models.values() if getattr(m, 'is_trained', False))
    return f"✅ Quantum Edge AI Bot LIVE | Активных моделей: {active}/{len(SYMBOLS)}", 200

@app.route('/health')
def health_check():
    return "OK", 200

# === Первичное обучение (в фоне) ===
def initial_training():
    logger.info("=== Первичное обучение всех моделей (5 эпох) ===")
    for symbol in SYMBOLS:
        logger.info(f"🧠 Обучаем {symbol}...")
        success = train_one(symbol, epochs=5)
        if success:
            lstm_models[symbol].is_trained = True
            logger.info(f"✅ {symbol} обучен и сохранён в weights/")
        else:
            logger.warning(f"❌ {symbol} не обучен — пропускаем")
        time.sleep(2)
    logger.info("=== Первичное обучение завершено ===")

# === Торговый цикл ===
def run_strategy():
    logger.info("=== Торговый цикл запущен ===")
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
                    logger.info(f"🎯 [СИГНАЛ] {side.upper()} {symbol} | P={lstm_prob:.2%} | ATR={atr:.2f} | Amt={amount:.4f}")
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

# === Запуск системы ===
def start_all():
    logger.info("=== СТАРТ СИСТЕМЫ (Web Service) ===")
    logger.info(f"📋 Используем {len(SYMBOLS)} пар: {SYMBOLS}")

    # 1. Скачиваем веса
    download_weights()

    # 2. Загружаем готовые
    trained = 0
    for s in SYMBOLS:
        model = load_model(s)
        if model:
            lstm_models[s] = model
            lstm_models[s].is_trained = True
            trained += 1
            logger.info(f"✅ {s} загружена из weights/")
        else:
            logger.warning(f"⚠️ {s} не найдена — будет обучена")

    # 3. Запускаем обучение в фоне
    if trained == 0:
        logger.info("🧠 Нет готовых моделей — начинаем первичное обучение (в фоне)...")
        threading.Thread(target=initial_training, daemon=True).start()
    else:
        missing = [s for s in SYMBOLS if not getattr(lstm_models[s], 'is_trained', False)]
        if missing:
            logger.info(f"🧠 Дообучаем недостающие (в фоне): {missing}")
            threading.Thread(target=lambda: [train_one(s, epochs=5) and setattr(lstm_models[s], 'is_trained', True) for s in missing], daemon=True).start()

    # 4. Торговля в фоне
    threading.Thread(target=run_strategy, daemon=True).start()

    # 5. Дообучение каждый час
    threading.Thread(target=sequential_trainer, args=(SYMBOLS, 3600, 2), daemon=True).start()

    # 6. Монитор позиций
    start_position_monitor(traders, SYMBOLS)

    logger.info("🚀 Web Service полностью запущен (Flask + background threads)")

# === Flask старт ===
if __name__ == "__main__":
    threading.Thread(target=start_all, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
