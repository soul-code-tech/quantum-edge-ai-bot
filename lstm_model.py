import os
import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout
from tensorflow.keras.optimizers import Adam
import pickle
import time

class LSTMPredictor:
    FINAL_FEATURES = ['volume', 'rsi_norm', 'sma_ratio', 'atr_norm',
                      'price_change', 'volume_change']

    def __init__(self, lookback=60, model_dir='weights'):
        self.lookback      = lookback
        self.model_dir     = model_dir
        self.model         = None
        self.scaler        = MinMaxScaler()
        self.feature_columns = ['close', 'volume', 'rsi', 'sma20', 'sma50', 'atr']
        self.model_path    = ''
        self.scaler_path   = ''
        self.last_training_time = 0

    # ---------- пути ----------
    def _get_model_paths(self, symbol: str):
        safe = symbol.replace('-', '_').replace('/', '_')
        m = os.path.join(self.model_dir, f"lstm_{safe}.weights.h5")
        s = os.path.join(self.model_dir, f"lstm_{safe}_scaler.pkl")
        return m, s

    # ---------- архитектура ----------
    def _create_model(self, input_shape):
        model = Sequential([
            LSTM(50, return_sequences=True, input_shape=input_shape),
            Dropout(0.2),
            LSTM(50, return_sequences=True),
            Dropout(0.2),
            LSTM(50),
            Dropout(0.2),
            Dense(25),
            Dense(1, activation='sigmoid')
        ])
        model.compile(optimizer=Adam(learning_rate=0.001),
                      loss='binary_crossentropy',
                      metrics=['accuracy'])
        return model

    # ---------- подготовка ----------
    def _prepare_features(self, df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
        feat = df[self.feature_columns].copy()
        feat['price_change']  = feat['close'].pct_change()
        feat['volume_change'] = feat['volume'].pct_change()
        feat['rsi_norm']      = feat['rsi'] / 100.0
        feat['sma_ratio']     = feat['sma20'] / feat['sma50']
        feat['atr_norm']      = feat['atr'] / feat['close']

        future_ret = feat['close'].pct_change(5).shift(-5)
        y = (future_ret > 0).astype(int).values
        X = feat[self.FINAL_FEATURES].dropna()
        y = y[X.index]
        return X, y

    def _create_sequences(self, data, labels=None):
        seq, targ = [], []
        for i in range(self.lookback, len(data)):
            seq.append(data[i - self.lookback:i])
            if labels is not None:
                targ.append(labels[i])
        return (np.array(seq), np.array(targ)) if labels is not None else np.array(seq)

    # ---------- сохранение / загрузка ----------
    def save(self, symbol: str):
        os.makedirs(self.model_dir, exist_ok=True)
        self.model.save_weights(self.model_path)
        with open(self.scaler_path, 'wb') as f:
            pickle.dump(self.scaler, f)
        print(f'💾 {symbol}: веса сохранены ➜ {self.model_path}')

    def load(self, symbol: str) -> bool:
        if not (os.path.exists(self.model_path) and os.path.exists(self.scaler_path)):
            return False
        self.model = self._create_model((self.lookback, len(self.FINAL_FEATURES)))
        self.model.load_weights(self.model_path)
        with open(self.scaler_path, 'rb') as f:
            self.scaler = pickle.load(f)
        print(f'📂 {symbol}: веса загружены из {self.model_path}')
        return True

    # ---------- обучение ----------
    def train_model(self, df: pd.DataFrame, symbol: str, epochs=5, is_initial=True):
        try:
            print(f"🧠 {'Первичное' if is_initial else 'Дообучение'} {symbol} на {epochs} эпох")
            X, y = self._prepare_features(df)
            if len(X) < self.lookback + 10:
                print(f'⚠️ {symbol}: мало данных после подготовки')
                return False

            X_scaled = self.scaler.fit_transform(X)
            X_seq, y_seq = self._create_sequences(X_scaled, y)
            if len(X_seq) == 0:
                return False

            if self.model is None:
                self.model = self._create_model((X_seq.shape[1], X_seq.shape[2]))

            hist = self.model.fit(X_seq, y_seq, epochs=epochs, batch_size=32,
                                  validation_split=0.1, verbose=1, shuffle=False)
            self.last_training_time = time.time()
            print(f"✅ {symbol}: обучено  loss={hist.history['loss'][-1]:.4f}  acc={hist.history['accuracy'][-1]:.4f}")
            return True
        except Exception as e:
            print(f'❌ {symbol}: ошибка обучения  {e}')
            return False

    # ---------- предсказание ----------
    def predict_next(self, df: pd.DataFrame) -> float:
        try:
            if self.model is None:
                return 0.5
            X, _ = self._prepare_features(df.tail(self.lookback + 5))
            if len(X) < self.lookback:
                return 0.5
            recent = X.tail(self.lookback)
            recent_scaled = self.scaler.transform(recent)
            seq = recent_scaled.reshape(1, self.lookback, -1)
            pred = float(self.model.predict(seq, verbose=0)[0][0])
            return pred
        except Exception as e:
            print(f'❌ predict_next: {e}')
            return 0.5

    # ---------- инициализация ----------
    def load_or_create_model(self, symbol: str) -> bool:
        self.model_path, self.scaler_path = self._get_model_paths(symbol)
        return self.load(symbol)
