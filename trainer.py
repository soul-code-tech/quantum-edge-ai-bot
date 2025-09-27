# trainer.py
import os, time, pickle, sys
from data_fetcher import get_bars
from lstm_model import LSTMPredictor
from strategy import calculate_strategy_signals

MODEL_DIR = "/tmp/lstm_weights"
os.makedirs(MODEL_DIR, exist_ok=True)

def model_path(symbol: str) -> str:
    return os.path.join(MODEL_DIR, symbol.replace("-", "") + ".pkl")

def heartbeat():
    """Фоновый тикер для Render – точка каждые 10 с."""
    def run():
        while True:
            time.sleep(10)
            print(".", end="", flush=True)   # Render видит активность
    threading.Thread(target=run, daemon=True).start()

import threading
heartbeat()          # запускаем сразу при импорте

def train_one(symbol: str, lookback: int = 60) -> bool:
    """Обучает одну пару (1 попытка) + heartbeat."""
    try:
        df = get_bars(symbol, "1h", 300)
        if df is None or len(df) < 200:
            print(f"\n⚠️  insufficient data for {symbol}")
            return False
        df = calculate_strategy_signals(df, 60)
        model = LSTMPredictor(lookback=lookback)
        model.train(df)                       # внутри есть print-ы → точки не мешают
        with open(model_path(symbol), "wb") as fh:
            pickle.dump({"scaler": model.scaler, "model": model.model}, fh)
        print(f"\n✅ LSTM обучилась для {symbol}")
        return True
    except Exception as e:
        print(f"\n❌ train error for {symbol}: {e}")
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
        print(f"\n⚠️ load model error for {symbol}: {e}")
        return None

def initial_train_all(symbols: list[str]) -> None:
    """Первичное обучение строго по одному разу + точки активности."""
    print("🧠 Начинаем первичное последовательное обучение...")
    ok = 0
    for s in symbols:
        if train_one(s):
            ok += 1
    print(f"\n🧠 Первичный цикл завершён: {ok}/{len(symbols)} пар обучены.")
    if ok == 0:
        raise RuntimeError("Ни одна пара не обучилась – проверьте данные.")

def sequential_trainer(symbols: list[str], interval: int = 600):
    """Бесконечное дообучение – одна пара за другим + точки."""
    idx = 0
    while True:
        sym = symbols[idx % len(symbols)]
        train_one(sym)
        idx += 1
        time.sleep(interval)
