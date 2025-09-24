# lstm_model.py
import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout

class LSTMPredictor:
    def __init__(self, lookback=60):
        self.lookback = lookback  # сколько свечей "помнить"
        self.model = None
        self.scaler = MinMaxScaler(feature_range=(0, 1))

    def prepare_data(self, df):
        # Берём только цену закрытия
        data = df['close'].values.reshape(-1, 1)
        # Нормализуем
        scaled_data = self.scaler.fit_transform(data)
        return scaled_data

    def create_sequences(self, data):
        X, y = [], []
        for i in range(self.lookback, len(data)):
            X.append(data[i-self.lookback:i, 0])
            # y = 1 если цена выросла, 0 если упала
            y.append(1 if data[i, 0] > data[i-1, 0] else 0)
        return np.array(X), np.array(y)

    def build_model(self):
        model = Sequential()
        model.add(LSTM(50, return_sequences=True, input_shape=(self.lookback, 1)))
        model.add(Dropout(0.2))
        model.add(LSTM(50, return_sequences=False))
        model.add(Dropout(0.2))
        model.add(Dense(25))
        model.add(Dense(1, activation='sigmoid'))  # 1 = рост, 0 = падение
        model.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])
        self.model = model

    def train(self, df):
        data = self.prepare_data(df)
        X, y = self.create_sequences(data)
        X = X.reshape((X.shape[0], X.shape[1], 1))  # Формат: (samples, timesteps, features)
        self.build_model()
        self.model.fit(X, y, batch_size=32, epochs=10, verbose=0)
        print("✅ LSTM обучена на исторических данных")

    def predict_next(self, df):
        if self.model is None:
            self.train(df)  # Обучаем, если ещё не обучена

        # Берём последние lookback свечей
        recent_data = df['close'].tail(self.lookback).values.reshape(-1, 1)
        scaled_recent = self.scaler.transform(recent_data)
        X_test = scaled_recent.reshape(1, self.lookback, 1)

        # Предсказываем вероятность роста
        prediction = self.model.predict(X_test, verbose=0)[0][0]
        return prediction > 0.55  # True = тренд вверх, если уверенность > 55%
