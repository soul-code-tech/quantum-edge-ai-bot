# lstm_model.py
import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler
from sklearn.linear_model import LogisticRegression
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Input, LSTM, Dense, Dropout

class LSTMPredictor:
    def __init__(self, lookback=60, name="lstm"):
        self.lookback = lookback
        self.name = name
        self.scaler = MinMaxScaler(feature_range=(0, 1))
        self.model = None
        self.is_trained = False

    # --------- те же методы, что и раньше ----------
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

    # --------- обучение на последних N баров (walk-forward) ----------
    def train(self, df, epochs=5, bars_back=400):
        data = self.prepare_features(df.tail(bars_back))
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


# =================== ENSEMBLE ===================
class EnsemblePredictor:
    def __init__(self, lookbacks=(60, 90)):
        self.models = [LSTMPredictor(lb, name=f"lstm{lb}") for lb in lookbacks]
        self.log_reg = LogisticRegression()

    def train(self, df, epochs=5, bars_back=400):
        # 1. обучаем каждую LSTM
        X_stack = None
        for m in self.models:
            m.train(df, epochs=epochs, bars_back=bars_back)
            prob = m.predict_next(df)
            col = np.full((len(df.tail(bars_back)), 1), prob)
            X_stack = col if X_stack is None else np.hstack([X_stack, col])

        # 2. логистическая регрессия на вероятностях моделей
        y = (df['close'].shift(-1) > df['close']).tail(bars_back).astype(int).values
        self.log_reg.fit(X_stack, y)
        self.is_trained = True

    def predict_next(self, df):
        if not getattr(self, 'is_trained', False):
            return 0.0
        X_new = np.array([[m.predict_next(df) for m in self.models]])
        return float(self.log_reg.predict_proba(X_new)[0, 1])
