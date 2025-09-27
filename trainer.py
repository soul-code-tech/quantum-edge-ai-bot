# trainer.py
import os
import time
import pickle
import threading
from data_fetcher import get_bars
from lstm_model import LSTMPredictor
from strategy import calculate_strategy_signals
import ccxt

MODEL_DIR = "/tmp/lstm_weights"
os.makedirs(MODEL_DIR, exist_ok=True)

def model_path(symbol: str) -> str:
    return os.path.join(MODEL_DIR, symbol.replace("-", "") + ".pkl")

def market_exists(symbol: str) -> bool:
    """Проверяет, существует ли рынок на BingX."""
    try:
        exchange = ccxt.bingx({'options': {'defaultType': 'swap'}})
        symbol_api = symbol.replace('-', '/')
        exchange.load_markets()
        return symbol_api in exchange.markets
    except Exception:
        return False

def train_one(symbol: str, lookback: int = 60, epochs: int = 5) -> bool:
    """Обучает одну пару: ≤ 25 с, heartbeat, без signal-alarm."""
    try:
        if not market_exists(symbol):
            print(f"\n❌ {symbol}: рынок не существует на BingX – пропускаем.")
            return False

        print(f"\n🧠 Обучаем {symbol} (epochs={epochs})...")

        # фоновый heartbeat – точка каждые 5 с
        stop_heartbeat = threading.Event()
        def tick():
            while not stop_heartbeat.is_set():
                time.sleep(5)
                print(".", end="", flush=True)
        threading.Thread(target=tick, daemon=True).start()

        # загружаем данные и считаем индикаторы
        df = get_bars(symbol, "1h", 300)
        if df is None or len(df) < 200:
            print(f"\n⚠️ Недостаточно данных для {symbol}")
            return False
        df = calculate_strategy_signals(df, 60)

        # обучаем (5 эпох ≈ 15-20 с на CPU)
        model = LSTMPredictor(lookback=lookback)
        model.train(df, epochs=epochs)          # переопределено ниже

        # сохраняем веса
        with open(model_path(symbol), "wb") as fh:
            pickle.dump({"scaler": model.scaler, "model": model.model}, fh)
        print(f"\n✅ LSTM обучилась для {symbol}")
        return True

    except Exception as e:
        print(f"\n❌ Ошибка обучения {symbol}: {e}")
        return False
    finally:
        stop_heartbeat.set()          # останавливаем heartbeat

def load_model(symbol: str, lookback: int = 60):
    path = model_path(symbol)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as fh:
            bundle = pickle.load(fh)
        m = LSTMPredictor(lookback=lookback)
        m.scaler = bundle["scaler"]
        m.model   = bundle["model"]
        m.is_trained = True
        return m
    except Exception as e:
        print(f"\n⚠️ Ошибка загрузки модели {symbol}: {e}")
        return None

def initial_train_all(symbols: list[str], epochs: int = 5) -> None:
    """Первичное обучение строго поочерёдно."""
    print("🧠 Начинаем первичное последовательное обучение...")
    ok = 0
    for s in symbols:
        if train_one(s, epochs=epochs):
            ok += 1
        time.sleep(2)  # пауза между парами
    print(f"\n🧠 Первичный цикл завершён: {ok}/{len(symbols)} пар обучены.")

def sequential_trainer(symbols: list[str], interval: int = 600, epochs: int = 5):
    """Дообучение каждые 10 минут (без таймаутов, с heartbeat)."""
    idx = 0
    while True:
        sym = symbols[idx % len(symbols)]
        train_one(sym, epochs=epochs)
        idx += 1
        time.sleep(interval)
