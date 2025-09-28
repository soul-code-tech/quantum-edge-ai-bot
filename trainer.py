# trainer.py
import os
import time
import pickle
import subprocess
import shutil
from data_fetcher import get_bars
from strategy import calculate_strategy_signals
from lstm_model import LSTMPredictor
import ccxt

MODEL_DIR = "/tmp/lstm_weights"
os.makedirs(MODEL_DIR, exist_ok=True)

REPO_ROOT   = os.path.dirname(os.path.abspath(__file__))
WEIGHTS_DIR = os.path.join(REPO_ROOT, "weights")
REPO_URL    = "github.com/soul-code-tech/quantum-edge-ai-bot.git"

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

        # Сохраняем только scaler + веса .weights.h5
        weight_file = model_path(symbol).replace(".pkl", ".weights.h5")
        model.model.save_weights(weight_file)
        with open(model_path(symbol), "wb") as fh:
            pickle.dump({"scaler": model.scaler}, fh)
        print(f"\n✅ LSTM обучилась для {symbol}")
        save_weights_to_github(symbol)
        return True
    except Exception as e:
        print(f"\n❌ Ошибка обучения {symbol}: {e}")
        return False

def save_weights_to_github(symbol: str):
    try:
        os.makedirs(WEIGHTS_DIR, exist_ok=True)
        src_pkl = model_path(symbol)
        src_h5  = src_pkl.replace(".pkl", ".weights.h5")
        dst_pkl = os.path.join(WEIGHTS_DIR, os.path.basename(src_pkl))
        dst_h5  = os.path.join(WEIGHTS_DIR, os.path.basename(src_h5))

        shutil.copy(src_pkl, dst_pkl)
        if os.path.exists(src_h5):
            shutil.copy(src_h5, dst_h5)

        os.chdir(REPO_ROOT)

        subprocess.run(["git", "config", "user.email", "bot@quantum-edge.ai"], check=True)
        subprocess.run(["git", "config", "user.name", "QuantumEdge-Bot"], check=True)
        subprocess.run(["git", "config", "http.postBuffer", "200M"], check=True)

        token = os.environ.get("GH_TOKEN")
        if not token:
            print("❌ GH_TOKEN не установлен – пропускаю пуш.")
            return

        subprocess.run(["git", "remote", "remove", "origin"], check=False)
        subprocess.run(
            ["git", "remote", "add", "origin",
             f"https://{token}@{REPO_URL}"],
            check=True
        )

        subprocess.run(["git", "checkout", "-B", "weights"], check=True)
        subprocess.run(["git", "add", "weights/"], check=True)
        subprocess.run(["git", "commit", "-m", f"update {symbol} weights"], check=True)

        for attempt in range(1, 4):
            try:
                subprocess.run(["git", "push", "--force-with-lease", "origin", "weights"], check=True)
                print(f"✅ Веса {symbol} отправлены в GitHub.")
                return
            except subprocess.CalledProcessError as e:
                print(f"⚠️  Push {symbol} попытка {attempt} не удалась: {e}")
                time.sleep(2 ** attempt)
        print(f"❌ Не удалось запушить веса {symbol} после 3 попыток.")
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
