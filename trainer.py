# trainer.py
import os
import time
import pickle
import logging
import requests
import zipfile
import shutil
from data_fetcher import get_bars
from strategy import calculate_strategy_signals
from lstm_model import LSTMPredictor
import ccxt
from sklearn.model_selection import train_test_split

logger = logging.getLogger("trainer")

MODEL_DIR = "/tmp/lstm_weights"
os.makedirs(MODEL_DIR, exist_ok=True)

REPO = "https://github.com/soul-code-tech/quantum-edge-ai-bot"
BRANCH = "weights"
ZIP_URL = f"{REPO}/archive/refs/heads/{BRANCH}.zip"

def model_path(symbol: str) -> str:
    return os.path.join(MODEL_DIR, symbol.replace("-", "") + ".pkl")

def download_weights():
    """Скачивает веса из ветки weights в /tmp/lstm_weights/"""
    logger.info("⬇️ Скачиваем веса из GitHub...")
    zip_path = "/tmp/weights.zip"
    try:
        r = requests.get(ZIP_URL, stream=True, timeout=30)
        if r.status_code != 200:
            logger.warning(f"GitHub вернул {r.status_code} — пропускаем загрузку")
            return
        with open(zip_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        if not zipfile.is_zipfile(zip_path):
            logger.warning("Скачанный файл не ZIP")
            os.remove(zip_path)
            return
        with zipfile.ZipFile(zip_path, 'r') as z:
            z.extractall("/tmp")
        src = f"/tmp/quantum-edge-ai-bot-{BRANCH}/weights"
        if os.path.exists(src):
            shutil.rmtree(MODEL_DIR, ignore_errors=True)
            shutil.move(src, MODEL_DIR)
            logger.info("✅ Веса загружены из GitHub")
        else:
            logger.warning("Папка weights не найдена в архиве")
        os.remove(zip_path)
    except Exception as e:
        logger.error(f"Ошибка загрузки весов: {e}")

def market_exists(symbol: str) -> bool:
    try:
        exchange = ccxt.bingx({'options': {'defaultType': 'swap'}, 'enableRateLimit': True})
        exchange.load_markets()
        return symbol in exchange.markets
    except Exception as e:
        logger.warning(f"market_exists({symbol}) error: {e}")
        return False

def validate_model(model, df, bars_back=400):
    try:
        data = model.prepare_features(df.tail(bars_back))
        if len(data) < 100:
            return False
        X, y = model.create_sequences(data)
        if len(X) < 20:
            return False
        X = X.reshape((X.shape[0], X.shape[1], 5))
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)
        model.build_model((X.shape[1], X.shape[2]))
        model.model.fit(X_train, y_train, epochs=1, verbose=0)
        _, acc = model.model.evaluate(X_test, y_test, verbose=0)
        logger.info(f"✅ Валидация {model_path('dummy').split('/')[-1]}: acc={acc:.3f}")
        return acc >= 0.52
    except Exception as e:
        logger.error(f"Валидация провалена: {e}")
        return False

def train_one(symbol: str, lookback: int = 60, epochs: int = 5) -> bool:
    try:
        if not market_exists(symbol):
            logger.info(f"❌ {symbol}: рынок не существует на BingX – пропускаем.")
            return False

        logger.info(f"🧠 Обучаем {symbol} (epochs={epochs})...")
        df = get_bars(symbol, "1h", 500)
        if df is None or len(df) < 300:
            logger.warning(f"⚠️ Недостаточно данных для {symbol}")
            return False
        df = calculate_strategy_signals(df, 60)

        model = LSTMPredictor(lookback=lookback)
        model.train(df, epochs=epochs)

        if not validate_model(model, df):
            logger.warning(f"⚠️ Модель {symbol} не прошла валидацию")
            return False

        # Сохраняем ТОЛЬКО локально (в /tmp)
        weight_file = model_path(symbol).replace(".pkl", ".weights.h5")
        model.model.save_weights(weight_file)
        with open(model_path(symbol), "wb") as fh:
            pickle.dump({"scaler": model.scaler}, fh)
        logger.info(f"✅ Модель {symbol} сохранена локально")
        return True

    except Exception as e:
        logger.error(f"❌ Ошибка обучения {symbol}: {e}")
        return False

def load_model(symbol: str, lookback: int = 60):
    path = model_path(symbol)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as fh:
            bundle = pickle.load(fh)
        m = LSTMPredictor(lookback=lookback)
        m.build_model((lookback, 5))
        m.model.load_weights(path.replace(".pkl", ".weights.h5"))
        m.is_trained = True
        return m
    except Exception as e:
        logger.error(f"⚠️ Ошибка загрузки модели {symbol}: {e}")
        return None
