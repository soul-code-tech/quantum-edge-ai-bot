# src/trainer.py
import os
import pickle
import logging
from lstm_model import LSTMPredictor

logger = logging.getLogger("trainer")
MODEL_DIR = "weights"

def model_path(symbol: str) -> str:
    clean = symbol.replace("-", "").replace("/", "").replace(":", "")
    return os.path.join(MODEL_DIR, clean + ".pkl")

def validate_model(model, df, bars_back=400):
    # Упрощённая валидация (можно оставить как заглушку)
    return True

def train_one(symbol: str, lookback: int = 60, epochs: int = 5, existing_model=None) -> bool:
    from data_fetcher import get_bars
    from strategy import calculate_strategy_signals

    try:
        df = get_bars(symbol, "1h", 500)
        if df is None or len(df) < 300:
            return False

        df = calculate_strategy_signals(df, 60)

        if existing_model is not None:
            model = existing_model
        else:
            model = LSTMPredictor(lookback=lookback)
            model.symbol = symbol
            model.build_model((lookback, 5))

        model.train(df, epochs=epochs, bars_back=400)

        if not validate_model(model, df):
            return False

        os.makedirs(MODEL_DIR, exist_ok=True)
        weight_file = model_path(symbol).replace(".pkl", ".weights.h5")
        model.model.save_weights(weight_file)
        with open(model_path(symbol), "wb") as fh:
            pickle.dump({"scaler": model.scaler}, fh)
        return True

    except Exception as e:
        logger.error(f"Ошибка обучения {symbol}: {e}")
        return False

def load_model(symbol: str, lookback: int = 60):
    path = model_path(symbol)
    weight_file = path.replace(".pkl", ".weights.h5")
    if not os.path.exists(path) or not os.path.exists(weight_file):
        return None
    try:
        with open(path, "rb") as fh:
            bundle = pickle.load(fh)
        m = LSTMPredictor(lookback=lookback)
        m.symbol = symbol
        m.build_model((lookback, 5))
        m.model.load_weights(weight_file)
        m.scaler = bundle["scaler"]
        m.is_trained = True
        return m
    except Exception as e:
        logger.error(f"Ошибка загрузки {symbol}: {e}")
        return None
