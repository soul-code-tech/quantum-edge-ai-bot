# trainer.py
import os
import time
import pickle
import shutil
from data_fetcher import get_bars
from strategy import calculate_strategy_signals
from lstm_model import LSTMPredictor
import ccxt

MODEL_DIR = "/tmp/lstm_weights"
os.makedirs(MODEL_DIR, exist_ok=True)

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
WEIGHTS_DIR = os.path.join(REPO_ROOT, "weights")

def model_path(symbol: str) -> str:
    return os.path.join(MODEL_DIR, symbol.replace("-", "") + ".pkl")

def market_exists(symbol: str) -> bool:
    try:
        exchange = ccxt.bingx({'options': {'defaultType': 'swap'}, 'enableRateLimit': True})
        exchange.load_markets()
        return symbol in exchange.markets
    except Exception as e:
        print(f"⚠️ Ошибка проверки рынка {symbol}: {e}")
        return False

def train_one(symbol: str, lookback: int = 60, epochs: int = 5) -> bool:
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
        model.train(df, epochs=epochs)

        # Сохраняем scaler + веса во временную папку
        weight_file = model_path(symbol).replace(".pkl", ".weights.h5")
        model.model.save_weights(weight_file)
        with open(model_path(symbol), "wb") as fh:
            pickle.dump({"scaler": model.scaler}, fh)
        print(f"\n✅ LSTM обучилась для {symbol}")

        # ❌ НЕ пытаемся пушить на Render — это невозможно
        # save_weights_to_github(symbol)  # ← УДАЛЕНО

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
        m.build_model((lookback, 5))
        m.model.load_weights(path.replace(".pkl", ".weights.h5"))
        m.is_trained = True
        return m
    except Exception as e:
        print(f"\n⚠️ Ошибка загрузки модели {symbol}: {e}")
        return None

def initial_train_all(symbols, epochs=5):
    print("🧠 Первичное обучение всех пар...")
    ok = 0
    for s in symbols:
        if train_one(s, epochs=epochs):
            ok += 1
        print(">", end="", flush=True)
        time.sleep(2)  # меньше нагрузки
    print(f"\n🧠 Первичное обучение завершено: {ok}/{len(symbols)} пар.")

def sequential_trainer(symbols, interval=600, epochs=3):
    idx = 0
    while True:
        sym = symbols[idx % len(symbols)]
        train_one(sym, epochs=epochs)
        idx += 1
        time.sleep(interval)
