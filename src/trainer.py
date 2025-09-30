# src/trainer.py
import os
from lstm_ensemble import LSTMEnsemble
from data_fetcher import get_bars
from strategy import calculate_strategy_signals

MODEL_DIR = "weights"

def model_path(symbol):
    clean = symbol.replace("/", "").replace(":", "").replace("-", "")
    return os.path.join(MODEL_DIR, clean + ".pkl")

def train_one(symbol, epochs=5):
    df = get_bars(symbol, "1h", 500)
    if df is None or len(df) < 400:
        return False
    df = calculate_strategy_signals(df)
    model = LSTMEnsemble()
    model.build_models()
    model.train(df, epochs=epochs)
    model.save(model_path(symbol))
    return True

def load_model(symbol):
    return LSTMEnsemble.load(model_path(symbol))
