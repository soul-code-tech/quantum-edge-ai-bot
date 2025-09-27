# trainer.py
import os
import time
import pickle
from data_fetcher import get_bars
from lstm_model import LSTMPredictor
from strategy import calculate_strategy_signals
import ccxt
from download_weights import download_weights   # ← новый импорт

MODEL_DIR = "/tmp/lstm_weights"
os.makedirs(MODEL_DIR, exist_ok=True)

def model_path(symbol: str) -> str:
    return os.path.join(MODEL_DIR, symbol.replace("-", "") + ".pkl")

def market_exists(symbol: str) -> bool:
    try:
        exchange = ccxt.bingx({'options': {'defaultType': 'swap'}})
        symbol_api = symbol.replace('-', '/')
        exchange.load_markets()
        return symbol_api in exchange.markets
    except Exception:
        return False

def train_one(symbol: str, lookback: int = 60, epochs: int = 5) -> bool:
    """Обучает одну пару: ≤ 25 с, heartbeat точками ВНУТРИ fit."""
    try:
        if not market_exists(symbol):
            print(f"\n❌ {symbol}: рынок не существует на BingX – пропускаем.")
            return False

        print(f"\n🧠 Обучаем {symbol} (epochs={epochs})...")

        df = get_bars(symbol, "1h", 300)
        if df is None or len(df) < 200:
            print(f"\n⚠️ Недостаточно данных для {symbol}")
            return False
        df = calculate_strategy_signals(df, 60)

        model = LSTMPredictor(lookback=lookback)
        model.train(df, epochs=epochs)          # внутри есть print-ы → точки идут

        with open(model_path(symbol), "wb") as fh:
            pickle.dump({"scaler": model.scaler, "model": model.model}, fh)
        print(f"\n✅ LSTM обучилась для {symbol}")
        return True

    except Exception as e:
        print(f"\n❌ Ошибка обучения {symbol}: {e}")
        return False

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

def initial_train_all(symbols, epochs=5):
    """Сначала качаем веса из GitHub, потом доучиваем недостающие."""
    download_weights()                            # ← новая строка
    print("🧠 Проверяем обученные пары...")
    ok = 0
    for s in symbols:
        if os.path.exists(model_path(s)):
            print(f"✅ {s} загружена из кэша")
            ok += 1
        else:
            print(f"🧠 Обучаем {s}...")
            if train_one(s, epochs=epochs):
                ok += 1
        # живой вывод между парами (без потоков)
        print(">", end="", flush=True)
        for _ in range(4):          # 4 × 0.5 с = 2 с
            time.sleep(0.5)
            print(">", end="", flush=True)
        print()
    print(f"\n🧠 Первичный цикл завершён: {ok}/{len(symbols)} пар обучены.")

def sequential_trainer(symbols, interval=600, epochs=5):
    """Дообучение раз в 10 минут (живой вывод внутри)."""
    idx = 0
    while True:
        sym = symbols[idx % len(symbols)]
        train_one(sym, epochs=epochs)
        idx += 1
        # «живая» задержка 10 мин (каждые 30 с выводим «.»)
        for _ in range(20):        # 20 × 30 с = 600 с
            time.sleep(30)
            print(".", end="", flush=True)
        print()                    # перевод строки после интервала
