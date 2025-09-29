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

# ...остальные функции без изменений...
