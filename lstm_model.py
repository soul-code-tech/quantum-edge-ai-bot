import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.models import Sequential, load_model
from tensorflow.keras.layers import LSTM, Dense, Dropout
from tensorflow.keras.callbacks import ModelCheckpoint
import os

class LSTMPredictor:
    def __init__(self, lookback=100, model_dir="models"):
        self.lookback = lookback
        self.scaler = MinMaxScaler(feature_range=(0, 1))
        self.model = None
        self.is_trained = False
        self.model_dir = model_dir
        os.makedirs(self.model_dir, exist_ok=True)  # ✅ Создаём папку, если её нет

    def prepare_features(self, df):
        df_features = df[['close', 'volume', 'rsi', 'sma20', 'atr']].copy().dropna()
        if len(df_features) == 0:
            raise ValueError("Нет данных после удаления NaN")
        scaled = self.scaler.fit_transform(df_features)
        return scaled

    def create_sequences(self, data):
        X, y = [], []
        for i in range(self.lookback, len(data)):
            X.append(data[i-self.lookback:i])
            y.append(1 if data[i, 0] > data[i-1, 0] else 0)  # ↑ = 1, ↓ = 0
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
        """Обучаем и сохраняем модель в файл"""
        try:
            data = self.prepare_features(df)
            X, y = self.create_sequences(data)
            if len(X) == 0:
                raise ValueError(f"Нет последовательностей для {symbol}")
            X = X.reshape((X.shape[0], X.shape[1], 5))

            if self.model is None:
                self.build_model(input_shape=(X.shape[1], X.shape[2]))

            model_path = os.path.join(self.model_dir, f"{symbol}.keras")
            checkpoint = ModelCheckpoint(model_path, monitor='loss', save_best_only=True, mode='min')

            print(f"🧠 Обучение модели для {symbol}... ({len(X)} последовательностей)")
            self.model.fit(X, y, epochs=10, batch_size=32, verbose=0, callbacks=[checkpoint])
            self.is_trained = True
            print(f"✅ {symbol}: LSTM обучена и сохранена в {model_path}")
        except Exception as e:
            print(f"⚠️ Ошибка обучения LSTM для {symbol}: {e}")
            raise e

    def predict_next(self, df, symbol):
        """Загружаем модель, если она есть — иначе возвращаем 50%"""
        model_path = os.path.join(self.model_dir, f"{symbol}.keras")

        if os.path.exists(model_path):
            try:
                self.model = load_model(model_path)
                self.is_trained = True
                print(f"🔄 {symbol}: Загружена сохранённая модель из {model_path}")
            except Exception as e:
                print(f"⚠️ {symbol}: Не удалось загрузить модель {model_path}: {e}")
                self.is_trained = False

        if not self.is_trained:
            print(f"⚠️ {symbol}: Модель ещё не обучена. Используется последнее состояние.")
            return 0.5

        try:
            data = self.prepare_features(df)
            last_sequence = data[-self.lookback:].reshape(1, self.lookback, 5)
            prob = self.model.predict(last_sequence, verbose=0)[0][0]
            return float(prob)
        except Exception as e:
            print(f"⚠️ Ошибка прогноза для {symbol}: {e}")
            return 0.5
