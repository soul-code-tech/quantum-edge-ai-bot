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

MODEL_DIR = os.getenv("WEIGHTS_DIR", "/tmp/lstm_weights")

def _log(stage: str, symbol: str, msg: str):
    logger.info(f"[{stage}] {symbol}: {msg}")

def model_path(symbol: str) -> str:
    return os.path.join(MODEL_DIR, symbol.replace("-", "") + ".pkl")

# ---------- EXPORTED FUNCTIONS ----------
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

def train_one(symbol: str, lookback: int = 60, epochs: int = 5) -> bool:
    try:
        from config import SYMBOLS          # локальный импорт, чтобы избежать цикла
        if symbol not in SYMBOLS:
            return False
        # (остальной код без изменений)
        _log("TRAIN", symbol, f"Начинаем обучение ({epochs} эпох)")
        df = get_bars(symbol, "1h", 500)
        if df is None or len(df) < 300:
            _log("TRAIN", symbol, "Недостаточно данных – пропускаем")
            return False
        df = calculate_strategy_signals(df, symbol, 60)
        model = LSTMPredictor(lookback=lookback)
        model.symbol = symbol
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
