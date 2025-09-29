# create_stub_weights.py
import os, pickle, numpy as np
from datetime import datetime
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout
import ccxt

MODEL_DIR = os.environ.get("WEIGHTS_DIR", "/tmp/lstm_weights")
os.makedirs(MODEL_DIR, exist_ok=True)

SYMBOLS = [
    'BTC-USDT', 'ETH-USDT', 'SOL-USDT', 'BNB-USDT',
    'XRP-USDT', 'DOGE-USDT', 'ADA-USDT', 'AVAX-USDT'
]

def create_stub_model(symbol: str):
    # минимальная модель
    model = Sequential([
        LSTM(32, return_sequences=True, input_shape=(60, 5)),
        Dropout(0.2),
        LSTM(16),
        Dense(1, activation='sigmoid')
    ])
    model.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])

    # фейковые веса (random)
    model.build((None, 60, 5))
    model.set_weights([np.random.randn(*w.shape) for w in model.get_weights()])

    # фейковый скейлер
    scaler = MinMaxScaler()
    scaler.fit(np.random.rand(100, 5))  # заглушка

    base = symbol.replace("-", "")
    model.save_weights(os.path.join(MODEL_DIR, f"{base}.weights.h5"))
    with open(os.path.join(MODEL_DIR, f"{base}.pkl"), "wb") as f:
        pickle.dump({"scaler": scaler}, f)
    print(f"✅ Заглушка создана: {base}")

if __name__ == "__main__":
    for s in SYMBOLS:
        create_stub_model(s)
    print("=== Все заглушки готовы ===")
