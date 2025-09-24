# lstm_model.py — Нейросетевой фильтр для стратегии
import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout

class LSTMPredictor:
    def __init__(self, lookback=60, features=5):
        self.lookback = lookback
        self.features = features  # close, volume, rsi, sma20, atr
        self.scaler = MinMaxScaler(feature_range=(0, 1))
        self.model = None
        self.is_trained = False

    def prepare_features(self, df):
        """Подготавливаем признаки: close, volume, rsi, sma20, atr"""
        df_features = df[['close', 'volume', 'rsi', 'sma20', 'atr']].copy()
        # Нормализуем
        scaled = self.scaler.fit_transform(df_features)
        return scaled

    def create_sequences(self, data):
        X, y = [], []
        for i in range(self.lookback, len(data)):
            X.append(data[i-self.lookback:i])  # 60 свечей по 5 признаков
            # y = 1 если цена выросла на следующей свече, 0 если упала
            y.append(1 if data[i, 0] > data[i-1, 0] else 0)
        return np.array(X), np.array(y)

    def build_model(self):
        model = Sequential()
        model.add(LSTM(64, return_sequences=True, input_shape=(self.lookback, self.features)))
        model.add(Dropout(0.3))
        model.add(LSTM(32, return_sequences=False))
        model.add(Dropout(0.3))
        model.add(Dense(16, activation='relu'))
        model.add(Dense(1, activation='sigmoid'))  # 0-1: вероятность роста
        model.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])
        self.model = model

    def train(self, df):
        print("🧠 Обучаем LSTM-модель на 200+ свечах...")
        data = self.prepare_features(df)
        X, y = self.create_sequences(data)
        X = X.reshape((X.shape[0], X.shape[1], self.features))  # (samples, timesteps, features)
        
        self.build_model()
        self.model.fit(X, y, epochs=10, batch_size=32, verbose=0)
        self.is_trained = True
        print("✅ LSTM обучена!")

    def predict_next(self, df):
        if not self.is_trained:
            self.train(df)
        
        data = self.prepare_features(df)
        last_sequence = data[-self.lookback:]  # последние 60 свечей
        last_sequence = last_sequence.reshape(1, self.lookback, self.features)
        
        prob = self.model.predict(last_sequence, verbose=0)[0][0]
        return prob  # возвращает число от 0 до 1
