# main.py
import os
import sys
import threading
import time
import logging
from flask import Flask
from data_fetcher import get_bars
from strategy import calculate_strategy_signals
from trader import BingXTrader
from lstm_model import LSTMPredictor
from trainer import train_one, load_model, download_weights, sequential_trainer
from position_monitor import start_position_monitor
from signal_cache import is_fresh_signal
from config import USE_DEMO, LEVERAGE, RISK_PERCENT, STOP_LOSS_PCT, TAKE_PROFIT_PCT, LSTM_CONFIDENCE, TIMEFRAME, SYMBOLS

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

# ---------- GitHub-push ветки weights ----------
import subprocess, tempfile, shutil
from datetime import datetime

GH_TOKEN  = os.getenv("GH_TOKEN")
REPO      = "soul-code-tech/quantum-edge-ai-bot"
GIT_EMAIL = "bot@quantum-edge-ai-bot.render.com"
GIT_NAME  = "QuantumEdgeBot"
# ---------- торговый цикл ----------
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
                    logger.info(f"🎯 [SIGNAL] {side.upper()} {symbol} | P={lstm_prob:.2%} | ATR={atr:.2f} | Amt={amount:.4f}")
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
def push_weights_to_github():
    try:
        logger.info("[GIT] Начинаем последовательное обучение + push в weights")
        work_dir = tempfile.mkdtemp()
        os.chdir(work_dir)

        clone_url = f"https://{GH_TOKEN}@github.com/{REPO}.git"
        subprocess.run(["git", "clone", "--branch", "weights", clone_url, "."], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(["git", "config", "user.email", GIT_EMAIL], check=True)
        subprocess.run(["git", "config", "user.name", GIT_NAME], check=True)

        # очищаем старые веса
        for f in os.listdir("."):
            if f.endswith((".pkl", ".weights.h5")):
                os.remove(f)

        weights_src = os.environ.get("WEIGHTS_DIR", "/tmp/lstm_weights")
        os.makedirs(weights_src, exist_ok=True)

        trained = 0
        for symbol in SYMBOLS:
            logger.info(f"[TRAIN] {symbol}: начинаем обучение (5 эпох)")
            if train_one(symbol, epochs=5):
                trained += 1
                logger.info(f"[TRAIN] {symbol}: обучена")
            else:
                logger.warning(f"[TRAIN] {symbol}: не обучена — пропускаем")
            time.sleep(1)  # не ддосим CPU

        if trained == 0:
            logger.warning("[GIT] Ни одна модель не обучена — нечего пушить")
            return

        for f in os.listdir(weights_src):
            if f.endswith((".pkl", ".weights.h5")):
                shutil.copy(os.path.join(weights_src, f), f)

        subprocess.run(["git", "add", "."], check=True)
        msg = f"авто: обновлены веса моделей {datetime.utcnow().strftime('%Y-%m-%d_%H:%M:%S')}"
        subprocess.run(["git", "commit", "-m", msg], check=True)
        subprocess.run(["git", "push", "origin", "weights"], check=True)

        logger.info("[GIT] ✅ Веса успешно отправлены в ветку weights")
    except Exception as e:
        logger.error(f"[GIT] ❌ Ошибка push: {e}")
    finally:
        os.chdir("/opt/render/project/src")
        shutil.rmtree(work_dir, ignore_errors=True)

# ---------- модифицированный start_all() ----------
def start_all():
    logger.info("=== START_ALL() ЗАПУЩЕН ===")
    download_weights()
    trained = 0
    for s in SYMBOLS:
        if load_model(s):
            lstm_models[s].is_trained = True
            trained += 1
            logger.info(f"[LOAD] {s}: модель загружена")
        else:
            logger.info(f"[LOAD] {s}: весов нет – обучимся внутри Render")
    if trained == 0:
        logger.info("[TRAIN] Нет готовых весов – запускаем последовательное обучение")
        push_weights_to_github()
    else:
        missing = [s for s in SYMBOLS if not getattr(lstm_models[s], 'is_trained', False)]
        if missing:
            logger.info(f"[TRAIN] Дообучаем недостающие: {missing}")
            for s in missing:
                if train_one(s, epochs=5):
                    lstm_models[s].is_trained = True
                    logger.info(f"[TRAIN] {s}: дообучена")
                else:
                    logger.warning(f"[TRAIN] {s}: дообучение провалено")
                time.sleep(1)

    logger.info(f"=== Итог: {sum(getattr(m,'is_trained',False) for m in lstm_models.values())}/{len(SYMBOLS)} моделей готовы ===")

    threading.Thread(target=run_strategy, daemon=True).start()
    threading.Thread(target=sequential_trainer, args=(SYMBOLS, 3600, 2), daemon=True).start()
    start_position_monitor(traders, SYMBOLS)

if __name__ == "__main__":
    threading.Thread(target=start_all, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
