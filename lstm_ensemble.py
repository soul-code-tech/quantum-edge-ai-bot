# src/lstm_ensemble.py
import os
import pickle
import numpy as np
from sklearn.linear_model import LogisticRegression
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout
from tensorflow.keras.optimizers import Adam
from sklearn.preprocessing import MinMaxScaler

class LSTMPredictor:
    def __init__(self, lookback=60):
        self.lookback = lookback
        self.model = None
        self.scaler = MinMaxScaler()
        self.is_trained = False

    def build_model(self, input_shape):
        if self.model is None:
            model = Sequential([
                LSTM(64, return_sequences=True, input_shape=input_shape),
                Dropout(0.3),
                LSTM(32, return_sequences=False),
                Dropout(0.3),
                Dense(16, activation='relu'),
                Dense(1, activation='sigmoid')
            ])
            model.compile(optimizer=Adam(0.001), loss='binary_crossentropy', metrics=['accuracy'])
            self.model = model

    def prepare_features(self, df):
        features = df[['open', 'high', 'low', 'close', 'volume']].values.astype(float)
        return self.scaler.fit_transform(features)

    def create_sequences(self, data):
        X, y = [], []
        for i in range(self.lookback, len(data) - 1):
            X.append(data[i - self.lookback:i])
            y.append(1.0 if data[i + 1, 3] > data[i, 3] else 0.0)
        return np.array(X), np.array(y)

    def train(self, df, epochs=5):
        data = self.prepare_features(df.tail(400))
        X, y = self.create_sequences(data)
        X = X.reshape((X.shape[0], X.shape[1], 5))
        self.model.fit(X, y, epochs=epochs, batch_size=32, verbose=0)
        self.is_trained = True

    def predict_proba(self, df):
        data = self.prepare_features(df.tail(self.lookback + 10))
        seq = data[-self.lookback:].reshape(1, self.lookback, 5)
        return float(self.model.predict(seq, verbose=0)[0, 0])

class LSTMEnsemble:
    def __init__(self):
        self.model1 = LSTMPredictor(lookback=60)
        self.model2 = LSTMPredictor(lookback=90)
        self.meta_model = LogisticRegression()
        self.is_trained = False

    def build_models(self):
        self.model1.build_model((60, 5))
        self.model2.build_model((90, 5))

    def train(self, df, epochs=5):
        self.model1.train(df, epochs)
        self.model2.train(df, epochs)
        # Обучаем мета-модель на валидационных данных (упрощённо)
        self.meta_model.fit(
            [[0.6, 0.7], [0.4, 0.3]],  # dummy
            [1, 0]
        )
        self.is_trained = True

    def predict_proba(self, df):
        p1 = self.model1.predict_proba(df)
        p2 = self.model2.predict_proba(df)
        ensemble_pred = self.meta_model.predict_proba([[p1, p2]])[0, 1]
        return float(ensemble_pred)

    def save(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.model1.model.save_weights(path.replace(".pkl", ".m1.h5"))
        self.model2.model.save_weights(path.replace(".pkl", ".m2.h5"))
        with open(path, "wb") as f:
            pickle.dump({
                "scaler1": self.model1.scaler,
                "scaler2": self.model2.scaler,
                "meta": self.meta_model
            }, f)

      @classmethod
    def load(cls, path):
        # Проверяем наличие файлов с новым расширением
        m1_path = path.replace(".pkl", ".m1.weights.h5")
        m2_path = path.replace(".pkl", ".m2.weights.h5")
        if not (os.path.exists(path) and os.path.exists(m1_path) and os.path.exists(m2_path)):
            return None
        
        obj = cls()
        obj.build_models()
        obj.model1.model.load_weights(m1_path)
        obj.model2.model.load_weights(m2_path)
        with open(path, "rb") as f:
            bundle = pickle.load(f)
        obj.model1.scaler = bundle["scaler1"]
        obj.model2.scaler = bundle["scaler2"]
        obj.meta_model = bundle["meta"]
        obj.is_trained = True
        return obj
