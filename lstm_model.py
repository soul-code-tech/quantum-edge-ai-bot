# lstm_model.py
import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Input, LSTM, Dense, Dropout

class LSTMPredictor:
    def __init__(self, lookback=60):
        self.lookback = lookback
        self.scaler = MinMaxScaler(feature_range=(0, 1))
        self.model = None
        self.is_trained = False

    def prepare_features(self, df):
        df_features = df[['close', 'volume', 'rsi', 'sma20', 'atr']].copy().dropna()
        return self.scaler.fit_transform(df_features)

    def create_sequences(self, data):
        X, y = [], []
        for i in range(self.lookback, len(data)):
            X.append(data[i - self.lookback:i])
            y.append(1 if data[i, 0] > data[i - 1, 0] else 0)
        return np.array(X), np.array(y)

    def build_model(self, input_shape):
        if self.model is not None:
            return
        model = Sequential()
        model.add(Input(shape=input_shape))
        model.add(LSTM(64, return_sequences=True))
        model.add(Dropout(0.3))
        model.add(LSTM(32, return_sequences=False))
        model.add(Dropout(0.3))
        model.add(Dense(16, activation='relu'))
        model.add(Dense(1, activation='sigmoid'))
        model.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])
        self.model = model

    def train(self, df, epochs=5):
        data = self.prepare_features(df)
        X, y = self.create_sequences(data)
        X = X.reshape((X.shape[0], X.shape[1], 5))
        self.build_model((X.shape[1], X.shape[2]))
        self.model.fit(X, y, epochs=epochs, batch_size=32, verbose=0)
        self.is_trained = True

    def predict_next(self, df):
        if not self.is_trained:
            return 0.0
        data = self.prepare_features(df)
        last_sequence = data[-self.lookback:].reshape(1, self.lookback, -1)
        return float(self.model.predict(last_sequence, verbose=0)[0][0])
