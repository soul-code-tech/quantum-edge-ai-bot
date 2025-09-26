# lstm_model.py — Без переобучения каждый раз
import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout

class LSTMPredictor:
    def __init__(self, lookback=60):
        self.lookback = lookback
        self.scaler = MinMaxScaler(feature_range=(0, 1))
        self.model = None
        self.is_trained = False

    def prepare_features(self, df):
        df_features = df[['close', 'volume', 'rsi', 'sma20', 'atr']].copy().dropna()
        scaled = self.scaler.fit_transform(df_features)
        return scaled

    def create_sequences(self, data):
        X, y = [], []
        for i in range(self.lookback, len(data)):
            X.append(data[i-self.lookback:i])
            y.append(1 if data[i, 0] > data[i-1, 0] else 0)
        return np.array(X), np.array(y)

    def build_model(self, input_shape):
        model = Sequential()
        model.add(LSTM(64, return_sequences=True, input_shape=input_shape))
        model.add(Dropout(0.3))
        model.add(LSTM(32, return_sequences=False))
        model.add(Dropout(0.3))
        model.add(Dense(16, activation='relu'))
        model.add(Dense(1, activation='sigmoid'))
        model.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])
        self.model = model

    def train(self, df):
        """Обучаем LSTM один раз в цикле"""
        try:
            data = self.prepare_features(df)
            X, y = self.create_sequences(data)
            X = X.reshape((X.shape[0], X.shape[1], 5))

            if self.model is None:
                self.build_model(input_shape=(X.shape[1], X.shape[2]))

            self.model.fit(X, y, epochs=10, batch_size=32, verbose=0)
            self.is_trained = True
            print("✅ LSTM обучена!")
        except Exception as e:
            print(f"⚠️ Ошибка обучения LSTM: {e}")

    def predict_next(self, df):
        """Только предсказание — без обучения"""
        if not self.is_trained:
            print("⚠️ Модель ещё не обучена. Используется последнее состояние.")
            return 0.5

        try:
            data = self.prepare_features(df)
            last_sequence = data[-self.lookback:].reshape(1, self.lookback, 5)
            prob = self.model.predict(last_sequence, verbose=0)[0][0]
            return prob
        except Exception as e:
            print(f"⚠️ Ошибка прогноза: {e}")
            return 0.5
