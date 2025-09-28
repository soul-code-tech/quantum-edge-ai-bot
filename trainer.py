# trainer.py
import os
import time
import pickle
import subprocess
import logging
from datetime import timedelta
from data_fetcher import get_bars, get_funding_rate
from strategy import calculate_strategy_signals
from lstm_model import EnsemblePredictor
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

        logger.info(f"🧠 Ensemble-обучение {symbol} ({epochs} эпох)")
        df = get_bars(symbol, "1h", 400)          # последние 400 баров ≈ 16 дней
        if df is None or len(df) < 300:
            logger.warning(f"{symbol}: мало данных – пропуск.")
            return False

        df = calculate_strategy_signals(df, symbol, 60)   # передаём symbol → funding фильтр

        # ========== Ensemble (2 LSTM + logistic) ==========
        ensemble = EnsemblePredictor(lookbacks=(60, 90))
        ensemble.train(df, epochs=epochs, bars_back=400)   # walk-forward 7 дней

        # сохраняем объект ensemble
        with open(model_path(symbol), "wb") as f:
            pickle.dump({"ensemble": ensemble}, f)

        logger.info(f"✅ Ensemble {symbol} обучён.")
        save_weights_to_github(symbol)
        return True
    except Exception as e:
        logger.error(f"Ошибка ensemble {symbol}: {e}")
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
        subprocess.run(["git", "push", "origin", "weights"], check=True)   # ← без --force
        logger.info(f"✅ Веса {symbol} отправлены.")
    except Exception as e:
        logger.error(f"Ошибка пуша {symbol}: {e}")

def load_model(symbol: str, lookback: int = 60):
    path = model_path(symbol)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as f:
            bundle = pickle.load(f)
        return bundle["ensemble"]          # возвращаем объект EnsemblePredictor
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

def sequential_trainer(symbols, interval=3600 * 24, epochs=2):
    """Каждые 24 ч проверяем, кому > 24 ч → переобучаем."""
    idx = 0
    while True:
        sym = symbols[idx % len(symbols)]
        if not is_model_fresh(sym):
            train_one(sym, epochs=epochs)
        idx += 1
        time.sleep(interval)
