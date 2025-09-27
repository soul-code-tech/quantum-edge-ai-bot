# trainer.py
import os, time, pickle, threading, signal, sys
from data_fetcher import get_bars
from lstm_model import LSTMPredictor
from strategy import calculate_strategy_signals

MODEL_DIR = "/tmp/lstm_weights"
os.makedirs(MODEL_DIR, exist_ok=True)

def model_path(symbol: str) -> str:
    return os.path.join(MODEL_DIR, symbol.replace("-", "") + ".pkl")

def heartbeat():
    """Фоновый тикер – точка каждые 5 с, чтобы Render не убивал контейнер."""
    def run():
        while True:
            time.sleep(5)
            print(".", end="", flush=True)
    threading.Thread(target=run, daemon=True).start()

heartbeat()          # запускаем сразу

class TimeoutError(Exception):
    pass

def _handle_timeout(signum, frame):
    raise TimeoutError

def train_one(symbol: str, lookback: int = 60, max_sec: int = 30) -> bool:
    """Обучает одну пару, но не дольше max_sec (30 с)."""
    try:
        print(f"\n🧠 Обучаем {symbol} (лимит {max_sec} с)...")
        df = get_bars(symbol, "1h", 300)
        if df is None or len(df) < 200:
            print(f"\n⚠️  insufficient data for {symbol}")
            return False
        df = calculate_strategy_signals(df, 60)

        # устанавливаем «будильник»
        old_handler = signal.signal(signal.SIGALRM, _handle_timeout)
        signal.alarm(max_sec)

        try:
            model = LSTMPredictor(lookback=lookback)
            model.train(df)                       # если занимает > max_sec – вылетит
        finally:
            signal.alarm(0)                       # снимаем будильник
            signal.signal(signal.SIGALRM, old_handler)

        with open(model_path(symbol), "wb") as fh:
            pickle.dump({"scaler": model.scaler, "model": model.model}, fh)
        print(f"\n✅ LSTM обучилась для {symbol}")
        return True
    except TimeoutError:
        print(f"\n⏰ Таймаут {max_sec} с для {symbol} – пропускаем.")
        return False
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
    """Первичное обучение строго по одному разу с таймаутом."""
    print("🧠 Начинаем первичное последовательное обучение (лимит 30 с на пару)...")
    ok = 0
    for s in symbols:
        if train_one(s, max_sec=30):
            ok += 1
    print(f"\n🧠 Первичный цикл завершён: {ok}/{len(symbols)} пар обучены.")
    if ok == 0:
        raise RuntimeError("Ни одна пара не обучилась – проверьте данные.")

def sequential_trainer(symbols: list[str], interval: int = 600):
    """Бесконечное дообучение – одна пара за другим (таймаут 30 с)."""
    idx = 0
    while True:
        sym = symbols[idx % len(symbols)]
        train_one(sym, max_sec=30)
        idx += 1
        time.sleep(interval)
