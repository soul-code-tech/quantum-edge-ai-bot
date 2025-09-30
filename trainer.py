# src/trainer.py
import os
from lstm_ensemble import LSTMEnsemble
from data_fetcher import get_bars
from strategy import calculate_strategy_signals

MODEL_DIR = "weights"

def model_path(symbol):
    clean = symbol.replace("/", "").replace(":", "").replace("-", "")
    return os.path.join(MODEL_DIR, clean + ".pkl")

def train_one(symbol: str, lookback: int = 60, epochs: int = 5, existing_model=None) -> bool:
    df = get_bars(symbol, "1h", 500)
    if df is None or len(df) < 400:
        return False
    df = calculate_strategy_signals(df)
    model = LSTMEnsemble()
    model.build_models()
    model.train(df, epochs=epochs)
    model.save(model_path(symbol))
    return True
    if existing_model is not None:
        model = existing_model
    else:
        model = LSTMPredictor(lookback=lookback)
        model.build_model((lookback, 5))

def load_model(symbol):
    return LSTMEnsemble.load(model_path(symbol))
