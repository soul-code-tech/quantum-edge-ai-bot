# trainer.py
import os
import time
import pickle
import subprocess
import logging
from datetime import datetime, timedelta
from data_fetcher import get_bars
from strategy import calculate_strategy_signals
from lstm_model import LSTMPredictor
import ccxt

logger = logging.getLogger("bot")

WEIGHTS_DIR = os.path.join(os.path.dirname(__file__), "weights")
os.makedirs(WEIGHTS_DIR, exist_ok=True)
REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
REPO_URL = "github.com/soul-code-tech/quantum-edge-ai-bot.git"

def model_path(symbol: str) -> str:
    return os.path.join(WEIGHTS_DIR, symbol.replace("-", "") + ".pkl")

def market_exists(symbol: str) -> bool:
    try:
        exchange = ccxt.bingx({"options": {"defaultType": "swap"}})
        exchange.load_markets()
        return symbol.replace("-", "") in exchange.markets
    except Exception as e:
        logger.error(f"Проверка рынка {symbol}: {e}")
        return False

def is_model_fresh(symbol: str, max_age_hours: int = 24) -> bool:
    path = model_path(symbol)
    if not os.path.exists(path):
        return False
    age_hours = (time.time() - os.path.getmtime(path)) / 3600
    return age_hours < max_age_hours

def train_one(symbol: str, lookback: int = 60, epochs: int = 5) -> bool:
    if is_model_fresh(symbol):
        logger.info(f"⏩ {symbol} свежая – пропуск.")
        return True
    try:
        if not market_exists(symbol):
            logger.warning(f"{symbol} нет на BingX – пропуск.")
            return False

        logger.info(f"🧠 Обучаем {symbol} ({epochs} эпох)")
        df = get_bars(symbol, "1h", 300)
        if df is None or len(df) < 200:
            logger.warning(f"{symbol}: мало данных – пропуск.")
            return False

        df = calculate_strategy_signals(df, 60)
        model = LSTMPredictor(lookback=lookback)
        model.train(df, epochs=epochs)

        weight_file = model_path(symbol).replace(".pkl", ".weights.h5")
        model.model.save_weights(weight_file)
        with open(model_path(symbol), "wb") as f:
            pickle.dump({"scaler": model.scaler}, f)

        logger.info(f"✅ {symbol} обучён.")
        save_weights_to_github(symbol)
        return True
    except Exception as e:
        logger.error(f"Ошибка обучения {symbol}: {e}")
        return False

def save_weights_to_github(symbol: str):
    try:
        os.chdir(REPO_ROOT)
        token = os.environ.get("GH_TOKEN")
        if not token:
            logger.warning("GH_TOKEN нет – пропускаю пуш.")
            return

        subprocess.run(["git", "config", "user.email", "bot@quantum-edge.ai"], check=True)
        subprocess.run(["git", "config", "user.name", "QuantumEdge-Bot"], check=True)

        subprocess.run(["git", "fetch", "origin", "weights"], check=False)
        subprocess.run(["git", "checkout", "-B", "weights"], check=True)
        subprocess.run(["git", "reset", "--hard", "origin/weights"], check=False)

        subprocess.run(["git", "add", "weights/"], check=True)
        subprocess.run(["git", "commit", "-m", f"update {symbol} weights"], check=True)

        for attempt in range(1, 4):
            try:
                subprocess.run(["git", "push", "origin", "weights"], check=True)
                logger.info(f"✅ Веса {symbol} отправлены.")
                return
            except subprocess.CalledProcessError as e:
                logger.warning(f"Push {symbol} попытка {attempt}: {e}")
                time.sleep(2 ** attempt)
        logger.error(f"❌ Не удалось запушить {symbol}")

    except Exception as e:
        logger.error(f"Ошибка пуша {symbol}: {e}")

def load_model(symbol: str, lookback: int = 60):
    path = model_path(symbol)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as f:
            bundle = pickle.load(f)
        m = LSTMPredictor(lookback=lookback)
        m.build_model((lookback, 5))
        m.model.load_weights(path.replace(".pkl", ".weights.h5"))
        m.scaler = bundle["scaler"]
        m.is_trained = True
        return m
    except Exception as e:
        logger.error(f"Загрузка модели {symbol}: {e}")
        return None

def initial_train_all(symbols, epochs=5):
    logger.info(f"Первичное обучение {len(symbols)} пар...")
    ok = 0
    for s in symbols:
        if train_one(s, epochs=epochs):
            ok += 1
        time.sleep(1)
    logger.info(f"Первичное обучение завершено: {ok}/{len(symbols)}.")

def sequential_trainer(symbols, interval=1800, epochs=2):
    idx = 0
    while True:
        sym = symbols[idx % len(symbols)]
        if not is_model_fresh(sym):
            train_one(sym, epochs=epochs)
        idx += 1
        time.sleep(interval)
