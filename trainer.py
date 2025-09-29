# trainer.py
import os
import time
import pickle
import logging
import requests
import zipfile
import shutil
from sklearn.model_selection import train_test_split
from data_fetcher import get_bars
from strategy import calculate_strategy_signals
from lstm_model import LSTMPredictor
import ccxt

logger = logging.getLogger("trainer")

MODEL_DIR = "/tmp/lstm_weights"
os.makedirs(MODEL_DIR, exist_ok=True)

def _log(stage: str, symbol: str, msg: str):
    logger.info(f"[{stage}] {symbol}: {msg}")

def model_path(symbol: str) -> str:
    return os.path.join(MODEL_DIR, symbol.replace("-", "") + ".pkl")

def download_weights():
    _log("WEIGHTS", "ALL", "⬇️ Начинаем скачивание весов с GitHub")
    zip_path = "/tmp/weights.zip"
    try:
        r = requests.get("https://github.com/soul-code-tech/quantum-edge-ai-bot/archive/refs/heads/weights.zip",
                         stream=True, timeout=30)
        if r.status_code != 200:
            _log("WEIGHTS", "ALL", f"⚠️ GitHub вернул {r.status_code} — пропускаем загрузку")
            return
        with open(zip_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        if not zipfile.is_zipfile(zip_path):
            _log("WEIGHTS", "ALL", "⚠️ Скачанный файл не ZIP")
            os.remove(zip_path)
            return
        with zipfile.ZipFile(zip_path, 'r') as z:
            z.extractall("/tmp")
        src = "/tmp/quantum-edge-ai-bot-weights/weights"
        if os.path.exists(src):
            shutil.rmtree(MODEL_DIR, ignore_errors=True)
            shutil.move(src, MODEL_DIR)
            _log("WEIGHTS", "ALL", "✅ Архив разархивирован, веса готовы к загрузке")
        else:
            _log("WEIGHTS", "ALL", "⚠️ Папка weights не найдена в архиве")
        os.remove(zip_path)
    except Exception as e:
        _log("WEIGHTS", "ALL", f"❌ Ошибка загрузки весов: {e}")

def market_exists(symbol: str) -> bool:
    try:
        exchange = ccxt.bingx({'options': {'defaultType': 'swap'}, 'enableRateLimit': True})
        exchange.load_markets()
        if symbol in exchange.markets:
            market = exchange.markets[symbol]
            return market.get('type') == 'swap' and market.get('active')
        return False
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
            _log("TRAIN", symbol, "Рынок не существует на BingX – пропускаем")
            return False

        _log("TRAIN", symbol, f"Начинаем обучение ({epochs} эпох)")
        df = get_bars(symbol, "1h", 500)
        if df is None or len(df) < 300:
            _log("TRAIN", symbol, "Недостаточно данных – пропускаем")
            return False

        df = calculate_strategy_signals(df, symbol, 60)
        model = LSTMPredictor(lookback=lookback)
        model.symbol = symbol  # для логов lstm
        model.train(df, epochs=epochs, bars_back=400)

        if not validate_model(model, df):
            _log("TRAIN", symbol, "Модель не прошла валидацию – пропускаем")
            return False

        weight_file = model_path(symbol).replace(".pkl", ".weights.h5")
        model.model.save_weights(weight_file)
        with open(model_path(symbol), "wb") as fh:
            pickle.dump({"scaler": model.scaler}, fh)
        _log("TRAIN", symbol, "Модель прошла валидацию, сохраняем веса")
        return True

    except Exception as e:
        _log("TRAIN", symbol, f"❌ Ошибка обучения: {e}")
        return False

def load_model(symbol: str, lookback: int = 60):
    path = model_path(symbol)
    if not os.path.exists(path):
        _log("LOAD", symbol, "Файл модели не найден")
        return None
    try:
        with open(path, "rb") as fh:
            bundle = pickle.load(fh)
        m = LSTMPredictor(lookback=lookback)
        m.symbol = symbol
        m.build_model((lookback, 5))
        m.model.load_weights(path.replace(".pkl", ".weights.h5"))
        m.is_trained = True
        _log("LOAD", symbol, "pickle-файл прочитан, веса загружены в модель")
        return m
    except Exception as e:
        _log("LOAD", symbol, f"❌ Ошибка загрузки модели: {e}")
        return None

def initial_train_all(symbols, epochs=5):
    logger.info(f"🧠 Первичное обучение {len(symbols)} пар: {symbols}")
    ok = 0
    for s in symbols:
        if train_one(s, epochs=epochs):
            ok += 1
            _log("TRAIN", s, "Обучение завершено")
        else:
            _log("TRAIN", s, "Обучение провалено")
        time.sleep(2)
    logger.info(f"🧠 Первичное обучение завершено: {ok}/{len(symbols)} обучено.")

def sequential_trainer(symbols, interval=3600, epochs=2):
    idx = 0
    while True:
        sym = symbols[idx % len(symbols)]
        _log("RETRAIN", sym, "Начинаем дообучение (2 эпохи)")
        if load_model(sym):
            _log("RETRAIN", sym, "Модель загружена – дообучаем")
            train_one(sym, epochs=epochs)
        else:
            _log("RETRAIN", sym, "Модель не найдена – обучаем с нуля")
            train_one(sym, epochs=epochs)
        idx += 1
        time.sleep(interval)
