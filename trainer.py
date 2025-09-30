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

# Используем папку 'weights' в корне проекта (а не /tmp)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.getenv("WEIGHTS_DIR", os.path.join(BASE_DIR, "weights"))
os.makedirs(MODEL_DIR, exist_ok=True)  # Создаём папку при импорте

def _log(stage: str, symbol: str, msg: str):
    logger.info(f"[{stage}] {symbol}: {msg}")

def model_path(symbol: str) -> str:
    clean_symbol = symbol.replace("-", "").replace("/", "")
    return os.path.join(MODEL_DIR, clean_symbol + ".pkl")

def download_weights():
    _log("WEIGHTS", "ALL", "⬇️ Начинаем скачивание весов с GitHub")
    zip_path = os.path.join("/tmp", "weights.zip")
    extract_to = "/tmp/quantum-edge-ai-bot-weights"
    
    try:
        url = "https://github.com/soul-code-tech/quantum-edge-ai-bot/archive/refs/heads/weights.zip"
        r = requests.get(url, stream=True, timeout=30)
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
        src = os.path.join(extract_to, "weights")
        if os.path.exists(src):
            shutil.rmtree(MODEL_DIR, ignore_errors=True)
            shutil.move(src, MODEL_DIR)
            os.makedirs(MODEL_DIR, exist_ok=True)
            _log("WEIGHTS", "ALL", "✅ Архив разархивирован, веса готовы к загрузке")
        else:
            _log("WEIGHTS", "ALL", "⚠️ Папка weights не найдена в архиве")
        os.remove(zip_path)
        shutil.rmtree(extract_to, ignore_errors=True)
    except Exception as e:
        _log("WEIGHTS", "ALL", f"❌ Ошибка загрузки весов: {e}")

def market_exists(symbol: str) -> bool:
    try:
        exchange = ccxt.bingx({'options': {'defaultType': 'swap'}, 'enableRateLimit': True})
        markets = exchange.load_markets()
        if symbol in markets:
            market = markets[symbol]
            return market.get('type') == 'swap' and market.get('active', False)
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
        # Модель уже должна быть построена и, возможно, иметь веса
        model.model.fit(X_train, y_train, epochs=1, verbose=0)
        _, acc = model.model.evaluate(X_test, y_test, verbose=0)
        logger.info(f"✅ Валидация модели для {model.symbol}: acc={acc:.3f}")
        return acc >= 0.52
    except Exception as e:
        logger.error(f"Валидация провалена: {e}")
        return False

def train_one(symbol: str, lookback: int = 60, epochs: int = 5, existing_model=None) -> bool:
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

        if existing_model is not None:
            model = existing_model
            _log("TRAIN", symbol, "Используем загруженную модель для дообучения")
        else:
            model = LSTMPredictor(lookback=lookback)
            model.symbol = symbol
            model.build_model((lookback, 5))  # Создаём архитектуру

        model.train(df, epochs=epochs, bars_back=400)

        if not validate_model(model, df):
            _log("TRAIN", symbol, "Модель не прошла валидацию – пропускаем")
            return False

        # Убедимся, что папка существует (на всякий случай)
        os.makedirs(MODEL_DIR, exist_ok=True)

        weight_file = model_path(symbol).replace(".pkl", ".weights.h5")
        model.model.save_weights(weight_file)
        with open(model_path(symbol), "wb") as fh:
            pickle.dump({"scaler": model.scaler}, fh)
        _log("TRAIN", symbol, "✅ Модель прошла валидацию, веса сохранены")
        return True

    except Exception as e:
        _log("TRAIN", symbol, f"❌ Ошибка обучения: {e}")
        return False

def load_model(symbol: str, lookback: int = 60):
    path = model_path(symbol)
    weight_file = path.replace(".pkl", ".weights.h5")
    if not os.path.exists(path) or not os.path.exists(weight_file):
        _log("LOAD", symbol, "Файл модели или весов не найден")
        return None
    try:
        with open(path, "rb") as fh:
            bundle = pickle.load(fh)
        m = LSTMPredictor(lookback=lookback)
        m.symbol = symbol
        m.build_model((lookback, 5))
        m.model.load_weights(weight_file)
        m.scaler = bundle["scaler"]
        m.is_trained = True
        _log("LOAD", symbol, "pickle-файл прочитан, веса загружены в модель")
        return m
    except Exception as e:
        _log("LOAD", symbol, f"❌ Ошибка загрузки модели: {e}")
        return None

def sequential_trainer(symbols, interval=3600, epochs=2):
    # Убедимся, что папка weights существует
    os.makedirs(MODEL_DIR, exist_ok=True)
    
    # Попробуем скачать веса, если папка пуста
    if not os.listdir(MODEL_DIR):
        download_weights()

    idx = 0
    while True:
        sym = symbols[idx % len(symbols)]
        _log("RETRAIN", sym, "Проверяем наличие модели для дообучения")
        
        model = load_model(sym, lookback=60)
        if model is not None:
            _log("RETRAIN", sym, "Модель загружена – дообучаем")
            success = train_one(sym, epochs=epochs, existing_model=model)
        else:
            _log("RETRAIN", sym, "Модель не найдена – обучаем с нуля")
            success = train_one(sym, epochs=epochs)
        
        if not success:
            _log("RETRAIN", sym, "Обучение завершилось неудачей")
        
        idx += 1
        time.sleep(interval)
