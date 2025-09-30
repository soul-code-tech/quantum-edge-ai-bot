# src/trainer.py
import os
from lstm_ensemble import LSTMEnsemble
from data_fetcher import get_bars
from strategy import calculate_strategy_signals

MODEL_DIR = "weights"

def model_path(symbol):
    base = symbol.split("/")[0]
    quote = symbol.split("/")[1].split(":")[0]
    clean = base + quote
    return os.path.join(MODEL_DIR, clean + ".pkl")

def train_one(symbol: str, lookback: int = 60, epochs: int = 5, existing_model=None) -> bool:
    df = get_bars(symbol, "1h", 500)
    if df is None or len(df) < 400:
        return False
    df = calculate_strategy_signals(df, 60)  # ← добавлен аргумент minutes

    # Используем существующую модель или создаём новую
    if existing_model is not None:
        model = existing_model
    else:
        model = LSTMEnsemble()
        model.build_models()

    try:
        model.train(df, epochs=epochs)
        os.makedirs(MODEL_DIR, exist_ok=True)
        model.save(model_path(symbol))
        return True
    except Exception as e:
        print(f"Ошибка обучения {symbol}: {e}")
        return False

def load_model(symbol):
    return LSTMEnsemble.load(model_path(symbol))
