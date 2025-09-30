# src/main.py
import os
import threading
import logging
import subprocess
import time
from flask import Flask
from trainer import load_model
from data_fetcher import get_bars, get_funding_rate
from strategy import calculate_strategy_signals

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
logger = logging.getLogger("main")

SYMBOLS = [
    "BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT",
    "XRP/USDT:USDT", "DOGE/USDT:USDT", "AVAX/USDT:USDT", "SHIB/USDT:USDT",
    "LINK/USDT:USDT", "PENGU/USDT:USDT"
]

models = {}
app = Flask(__name__)

@app.route("/health")
def health():
    return {"status": "ok"}

def clone_weights():
    if not os.path.exists("weights/.gitkeep"):
        subprocess.run([
            "git", "clone", "--branch", "weights", "--depth", "1",
            "https://github.com/soul-code-tech/quantum-edge-ai-bot.git",
            "weights"
        ], check=True)

def initialize_models():
    clone_weights()
    for s in SYMBOLS:
        model = load_model(s)
        if model:
            models[s] = model
            logger.info(f"✅ Модель {s} загружена")
        else:
            logger.warning(f"⚠️ Модель {s} не найдена")

def trade_loop():
    while True:
        for symbol in SYMBOLS:
            try:
                model = models.get(symbol)
                if not model or not model.is_trained:
                    continue

                df = get_bars(symbol, "1h", 200)
                if df is None or len(df) < 100:
                    continue

                df = calculate_strategy_signals(df)
                prob = model.predict_proba(df)
                funding = get_funding_rate(symbol)

                long_score = df['long_score'].iloc[-1]
                trend = df['trend_score'].iloc[-1]

                # LONG
                if (long_score >= 5 and trend >= 3 and prob > 0.75 and
                    funding < 0.05):  # funding < +0.05%
                    logger.info(f"📈 LONG {symbol} | prob={prob:.2f} | funding={funding:.3f}%")

                # SHORT
                elif (long_score <= 2 and trend <= 1 and prob < 0.25 and
                      funding > -0.05):  # funding > -0.05%
                    logger.info(f"📉 SHORT {symbol} | prob={prob:.2f} | funding={funding:.3f}%")

            except Exception as e:
                logger.error(f"Ошибка торговли {symbol}: {e}")

        time.sleep(60)

if __name__ == "__main__":
    logger.info("✅ Quantum Edge AI Bot (только торговля)")
    initialize_models()
    threading.Thread(target=trade_loop, daemon=True).start()

    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
