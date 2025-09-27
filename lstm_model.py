# lstm_model.py — ИСПРАВЛЕННАЯ ВЕРСИЯ — БЕЗ ОПАСНЫХ ПОВТОРНЫХ ОБУЧЕНИЙ
import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.models import Sequential, load_model
from tensorflow.keras.layers import LSTM, Dense, Dropout
import os

class LSTMPredictor:
    def __init__(self, lookback=60, model_dir="models"):
        self.lookback = lookback
        self.scaler = MinMaxScaler(feature_range=(0, 1))
        self.model = None
        self.is_trained = False
        self.model_dir = model_dir
        os.makedirs(self.model_dir, exist_ok=True)

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

    def train(self, df, symbol):
        """Обучаем и сохраняем модель в файл — только один раз!"""
        print(f"🧠 Обучаем LSTM-модель для {symbol}...")
        data = self.prepare_features(df)
        X, y = self.create_sequences(data)
        if len(X) == 0:
            print(f"⚠️ Недостаточно данных для {symbol} после обработки")
            return

        X = X.reshape((X.shape[0], X.shape[1], 5))
        self.build_model(input_shape=(X.shape[1], X.shape[2]))
        self.model.fit(X, y, epochs=10, batch_size=32, verbose=0)

        # ✅ СОХРАНЯЕМ МОДЕЛЬ В ФАЙЛ — ЭТО КЛЮЧЕВОЕ!
        model_path = os.path.join(self.model_dir, f"{symbol}.keras")
        self.model.save(model_path)
        self.is_trained = True
        print(f"✅ LSTM обучена и сохранена в {model_path}")

    def predict_next(self, df, symbol):
        """Загружаем модель, если есть — иначе обучаем и сохраняем"""
        model_path = os.path.join(self.model_dir, f"{symbol}.keras")

        # ✅ ПРОВЕРКА: есть ли сохранённая модель?
        if os.path.exists(model_path):
            try:
                self.model = load_model(model_path)
                self.is_trained = True
                print(f"🔄 Загружена сохранённая модель для {symbol}")
            except Exception as e:
                print(f"⚠️ Не удалось загрузить модель {model_path}: {e}")
                self.is_trained = False

        # ✅ ЕСЛИ НЕТ — ОБУЧАЕМ И СОХРАНЯЕМ (ТОЛЬКО ОДИН РАЗ!)
        if not self.is_trained:
            self.train(df, symbol)

        # ✅ ПРОГНОЗ
        data = self.prepare_features(df)
        last_sequence = data[-self.lookback:].reshape(1, self.lookback, 5)
        prob = self.model.predict(last_sequence, verbose=0)[0][0]
        return prob
