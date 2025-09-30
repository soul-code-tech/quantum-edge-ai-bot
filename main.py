# main.py
import os
import threading
import logging
from flask import Flask
import ccxt
from data_fetcher import get_bars
from strategy import calculate_strategy_signals
from lstm_model import LSTMPredictor
from trainer import load_model, train_one

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("main")

# Символы
SYMBOLS = [
    "BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT",
    "XRP/USDT:USDT", "DOGE/USDT:USDT", "AVAX/USDT:USDT", "SHIB/USDT:USDT",
    "LINK/USDT:USDT", "PENGU/USDT:USDT"
]

# Глобальные модели
lstm_models = {}

app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Quantum Edge AI Bot is running!"

@app.route("/health")
def health():
    return {"status": "ok"}

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

def initialize_models():
    """Инициализирует модели: загружает или создаёт новые."""
    global lstm_models
    for s in SYMBOLS:
        if not market_exists(s):
            logger.warning(f"Рынок {s} недоступен — пропускаем")
            continue
        model = load_model(s, lookback=60)
        if model is not None:
            lstm_models[s] = model
            logger.info(f"✅ Модель для {s} загружена")
        else:
            logger.info(f"🆕 Модель для {s} не найдена — создаём заготовку")
            lstm_models[s] = LSTMPredictor(lookback=60)  # ← БЕЗ model_dir!

def run_strategy():
    """Основной цикл дообучения (в фоне)."""
    initialize_models()
    while True:
        for symbol in SYMBOLS:
            try:
                logger.info(f"🔄 Дообучение модели для {symbol}")
                model = lstm_models.get(symbol)
                if model and hasattr(model, 'is_trained') and model.is_trained:
                    success = train_one(symbol, epochs=2, existing_model=model)
                else:
                    success = train_one(symbol, epochs=2)
                if success:
                    # Обновляем модель в памяти
                    updated = load_model(symbol, lookback=60)
                    if updated:
                        lstm_models[symbol] = updated
                        logger.info(f"🧠 Модель {symbol} обновлена в памяти")
            except Exception as e:
                logger.error(f"❌ Ошибка дообучения {symbol}: {e}")
        logger.info("⏳ Ждём 30 минут до следующего цикла дообучения...")
        import time
        time.sleep(1800)  # 30 минут

if __name__ == "__main__":
    logger.info("✅ [СТАРТ] Quantum Edge AI Bot запущен на 10 криптопарах")
    logger.info(f"📊 ПАРЫ: {', '.join([s.replace('/USDT:USDT', '') for s in SYMBOLS])}")
    logger.info("🧠 LSTM: порог уверенности 75.0%")
    logger.info("💸 Риск: 1.0% от депозита на сделку")
    logger.info("⛔ Стоп-лосс: 1.5% | 🎯 Тейк-профит: 3.0%")
    logger.info("📈 Трейлинг-стоп: 1.0% от цены")
    logger.info("⏳ Кулдаун: 3600 сек. на пару")
    logger.info("🔄 Дообучение: каждые 30 минут на 2 эпохах")

    # Запуск дообучения в фоне
    strategy_thread = threading.Thread(target=run_strategy, daemon=True)
    strategy_thread.start()

    # Запуск Flask-сервера на порту 10000 (Render)
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
