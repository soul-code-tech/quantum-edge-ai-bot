# main.py
# 1. МГНОВЕННО ОТКРЫВАЕМ ПОРТ — до импортов
import os, socket, threading, time
def _instant_port():
    port = int(os.environ.get("PORT", 10000))
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0", port))
        s.listen(5)
        while True:
            conn, _ = s.accept()
            try:
                conn.sendall(b"HTTP/1.1 200 OK\r\nConnection: close\r\n\r\nOK")
            finally:
                conn.close()
threading.Thread(target=_instant_port, daemon=True).start()
time.sleep(0.3)

# 2. ОСТАЛЬНЫЕ ИМПОРТЫ
import sys, logging
from flask import Flask
from data_fetcher import get_bars
from strategy import calculate_strategy_signals
from trader import BingXTrader
from lstm_model import LSTMPredictor
from trainer import train_one, load_model, download_weights, sequential_trainer
from position_monitor import start_position_monitor
from signal_cache import is_fresh_signal
from config import (USE_DEMO, LEVERAGE, RISK_PERCENT, STOP_LOSS_PCT,
                    TAKE_PROFIT_PCT, LSTM_CONFIDENCE, TIMEFRAME, SYMBOLS)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("main")

app = Flask(__name__)
lstm_models = {s: LSTMPredictor() for s in SYMBOLS}
traders = {s: BingXTrader(symbol=s, use_demo=USE_DEMO, leverage=LEVERAGE) for s in SYMBOLS}

@app.route("/")
def wake_up():
    active = sum(1 for m in lstm_models.values() if getattr(m, 'is_trained', False))
    return f"✅ Quantum Edge AI Bot LIVE | Активных моделей: {active}/{len(SYMBOLS)}", 200

@app.route("/health")
def health_check():
    return "OK", 200

def initial_training():
    logger.info("=== Первичное обучение (5 эпох) ===")
    for s in SYMBOLS:
        if train_one(s, epochs=5):
            lstm_models[s].is_trained = True
            logger.info(f"✅ {s} обучен")
        else:
            logger.warning(f"❌ {s} не обучен")
        time.sleep(2)
    logger.info("=== Первичное обучение завершено ===")

def run_strategy():
    logger.info("=== Торговый цикл ===")
    while True:
        try:
            for s in SYMBOLS:
                if not getattr(lstm_models[s], 'is_trained', False):
                    continue
                df = get_bars(s, TIMEFRAME, 500)
                if df is None or len(df) < 100:
                    continue
                df = calculate_strategy_signals(df, s, 60)
                if not is_fresh_signal(s, df):
                    continue
                buy = df['buy_signal'].iloc[-1]
                sell = df['sell_signal'].iloc[-1]
                long_score = df['long_score'].iloc[-1]
                short_score = df['short_score'].iloc[-1]
                prob = lstm_models[s].predict_next(df)
                if ((buy and long_score >= 5) or (sell and short_score >= 5)) and prob > LSTM_CONFIDENCE:
                    side = 'buy' if buy else 'sell'
                    atr = df['atr'].iloc[-1]
                    amount = max(0.001, (100 * RISK_PERCENT / 100) / (atr * 1.5))
                    logger.info(f"🎯 {side.upper()} {s} P={prob:.2%}")
                    traders[s].place_order(side, amount, STOP_LOSS_PCT, TAKE_PROFIT_PCT)
            time.sleep(60)
        except Exception as e:
            logger.error(f"Стратегия: {e}")
            time.sleep(60)

def start_all():
    logger.info("=== СТАРТ Web Service ===")
    download_weights()
    trained = 0
    for s in SYMBOLS:
        if load_model(s):
            lstm_models[s].is_trained = True
            trained += 1
    if trained == 0:
        threading.Thread(target=initial_training, daemon=True).start()
    else:
        missing = [s for s in SYMBOLS if not getattr(lstm_models[s], 'is_trained', False)]
        if missing:
            threading.Thread(target=lambda: [train_one(s, epochs=5) and setattr(lstm_models[s], 'is_trained', True) for s in missing], daemon=True).start()
    threading.Thread(target=run_strategy, daemon=True).start()
    threading.Thread(target=sequential_trainer, args=(SYMBOLS, 3600, 2), daemon=True).start()
    start_position_monitor(traders, SYMBOLS)
    logger.info("🚀 Web Service + background threads запущены")

if __name__ == "__main__":
    start_all()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
