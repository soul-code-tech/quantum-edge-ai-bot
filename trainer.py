# trainer.py
import os
import time
import pickle
import subprocess
import shutil
from data_fetcher import get_bars
from lstm_model import LSTMPredictor
from strategy import calculate_strategy_signals
import ccxt

MODEL_DIR = "/tmp/lstm_weights"
os.makedirs(MODEL_DIR, exist_ok=True)

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
WEIGHTS_REPO_DIR = os.path.join(REPO_ROOT, "weights")

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

        with open(model_path(symbol), "wb") as fh:
            pickle.dump({"scaler": model.scaler, "model": model.model}, fh)
        print(f"\n✅ LSTM обучилась для {symbol}")

        # Сохраняем в GitHub
        save_weights_to_github(symbol)
        return True

    except Exception as e:
        print(f"\n❌ Ошибка обучения {symbol}: {e}")
        return False

def save_weights_to_github(symbol: str):
    try:
        os.makedirs(WEIGHTS_REPO_DIR, exist_ok=True)
        src = model_path(symbol)
        dst = os.path.join(WEIGHTS_REPO_DIR, symbol.replace("-", "") + ".pkl")
        shutil.copy(src, dst)

        os.chdir(REPO_ROOT)

        # ➜➜➜  НАСТРОЙКА Git-автора  ➜➜➜
        subprocess.run(["git", "config", "user.email", "bot@quantum-edge.ai"], check=True)
        subprocess.run(["git", "config", "user.name", "QuantumEdge-Bot"], check=True)

        subprocess.run(["git", "checkout", "-B", "weights"], check=True)
        subprocess.run(["git", "add", "weights/"], check=True)
        subprocess.run(["git", "commit", "-m", f"update {symbol} weights"], check=True)
        subprocess.run(["git", "push", "origin", "weights"], check=True)
        print(f"✅ Веса {symbol} отправлены в GitHub.")
    except Exception as e:
        print(f"❌ Ошибка пуша в GitHub для {symbol}: {e}")

def load_model(symbol: str, lookback: int = 60):
    path = model_path(symbol)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as fh:
            bundle = pickle.load(fh)
        m = LSTMPredictor(lookback=lookback)
        m.scaler = bundle["scaler"]
        m.model = bundle["model"]
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
        for _ in range(4):
            time.sleep(0.5)
            print(">", end="", flush=True)
        print()
    print(f"\n🧠 Первичное обучение завершено: {ok}/{len(symbols)} пар.")

def sequential_trainer(symbols, interval=600, epochs=5):
    idx = 0
    while True:
        sym = symbols[idx % len(symbols)]
        train_one(sym, epochs=epochs)
        idx += 1
        for _ in range(20):
            time.sleep(30)
            print(".", end="", flush=True)
        print()
