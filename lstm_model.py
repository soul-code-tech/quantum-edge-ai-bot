# lstm_model.py
import os
import numpy as np
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout
from tensorflow.keras.optimizers import Adam

class LSTMPredictor:
    def __init__(self, lookback=60):
        self.lookback = lookback
        self.model = None
        self.scaler = MinMaxScaler(feature_range=(0, 1))
        self.is_trained = False
        self.symbol = None

    def build_model(self, input_shape):
        if self.model is not None:
            return
        model = Sequential([
            LSTM(50, return_sequences=True, input_shape=input_shape),
            Dropout(0.2),
            LSTM(50, return_sequences=False),
            Dropout(0.2),
            Dense(25),
            Dense(1)
        ])
        model.compile(optimizer=Adam(learning_rate=0.001), loss='mse', metrics=['mae'])
        self.model = model

    def prepare_features(self, df):
        if df is None or len(df) == 0:
            return np.array([])
        features = df[['open', 'high', 'low', 'close', 'volume']].values.astype(float)
        scaled = self.scaler.fit_transform(features)
        return scaled

    def create_sequences(self, data):
        X, y = [], []
        for i in range(self.lookback, len(data)):
            X.append(data[i - self.lookback:i])
            y.append(data[i, 3])  # close
        return np.array(X), np.array(y)

    def train(self, df, epochs=5, bars_back=400):
        if self.model is None:
            raise RuntimeError("Модель не построена. Вызовите build_model().")
        data = self.prepare_features(df.tail(bars_back))
        if len(data) < self.lookback + 10:
            raise ValueError("Недостаточно данных.")
        X, y = self.create_sequences(data)
        if len(X) == 0:
            raise ValueError("Не удалось создать последовательности.")
        X = X.reshape((X.shape[0], X.shape[1], 5))
        self.model.fit(X, y, epochs=epochs, batch_size=32, verbose=1)
        self.is_trained = True

    def predict(self, df):
        if not self.is_trained or self.model is None:
            raise RuntimeError("Модель не обучена.")
        data = self.prepare_features(df.tail(self.lookback + 10))
        if len(data) < self.lookback:
            raise ValueError("Недостаточно данных для предсказания.")
        last_seq = data[-self.lookback:]
        last_seq = last_seq.reshape((1, self.lookback, 5))
        pred_scaled = self.model.predict(last_seq, verbose=0)
        dummy = np.zeros((1, 5))
        dummy[0, 3] = pred_scaled[0, 0]
        pred = self.scaler.inverse_transform(dummy)[0, 3]
        return pred
