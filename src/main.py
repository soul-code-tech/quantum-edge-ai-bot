# src/main.py
import os
import threading
import logging
import subprocess
import time
from flask import Flask
from lstm_model import LSTMPredictor
from trainer import load_model

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
logger = logging.getLogger("main")

SYMBOLS = [
    "BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT",
    "XRP/USDT:USDT", "DOGE/USDT:USDT", "AVAX/USDT:USDT", "SHIB/USDT:USDT",
    "LINK/USDT:USDT", "PENGU/USDT:USDT"
]

lstm_models = {}
app = Flask(__name__)

@app.route("/health")
def health():
    return {"status": "ok"}

def clone_weights():
    """Загружает веса из ветки weights при старте."""
    if not os.path.exists("weights/.gitkeep"):
        try:
            subprocess.run([
                "git", "clone", "--branch", "weights", "--depth", "1",
                "https://github.com/soul-code-tech/quantum-edge-ai-bot.git",
                "weights"
            ], check=True)
        except Exception as e:
            logger.error(f"Не удалось загрузить веса: {e}")

def initialize_models():
    clone_weights()
    for s in SYMBOLS:
        model = load_model(s, lookback=60)
        if model:
            lstm_models[s] = model
            logger.info(f"✅ Модель {s} загружена")
        else:
            logger.warning(f"⚠️ Модель {s} не найдена")

def trade_loop():
    """Здесь будет ваша логика торговли с фильтром LSTM."""
    while True:
        for symbol in SYMBOLS:
            model = lstm_models.get(symbol)
            if model and model.is_trained:
                logger.info(f"🔍 Анализ {symbol} с LSTM...")
                # Ваша логика сигналов + LSTM-фильтр
        time.sleep(60)

if __name__ == "__main__":
    logger.info("✅ Quantum Edge AI Bot запущен (только торговля)")
    initialize_models()
    threading.Thread(target=trade_loop, daemon=True).start()

    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
