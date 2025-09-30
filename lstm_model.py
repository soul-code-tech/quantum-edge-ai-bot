import os
import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.models import Sequential, load_model
from tensorflow.keras.layers import LSTM, Dense, Dropout
from tensorflow.keras.optimizers import Adam
import pickle
import time

class LSTMPredictor:
    def __init__(self, lookback=60, model_dir='weights'):
        self.lookback = lookback
        self.model_dir = model_dir
        self.model = None
        self.scaler = MinMaxScaler()
        self.feature_columns = ['close', 'volume', 'rsi', 'sma20', 'sma50', 'atr']
        self.model_path = None
        self.scaler_path = None
        self.last_training_time = 0
        
    def _get_model_paths(self, symbol):
        """Генерирует пути для модели и скейлера для конкретного символа"""
        safe_symbol = symbol.replace('-', '_').replace('/', '_')
        model_filename = f"lstm_{safe_symbol}.weights.h5"
        scaler_filename = f"lstm_{safe_symbol}_scaler.pkl"
        
        model_path = os.path.join(self.model_dir, model_filename)
        scaler_path = os.path.join(self.model_dir, scaler_filename)
        
        return model_path, scaler_path
    
    def _create_model(self, input_shape):
        """Создает архитектуру LSTM модели"""
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
        
        model.compile(
            optimizer=Adam(learning_rate=0.001),
            loss='binary_crossentropy',
            metrics=['accuracy']
        )
        
        return model
    
    def _prepare_features(self, df):
        """Подготавливает признаки для обучения"""
        features_df = df[self.feature_columns].copy()
        
        # Добавляем технические индикаторы как признаки
        features_df['price_change'] = features_df['close'].pct_change()
        features_df['volume_change'] = features_df['volume'].pct_change()
        features_df['rsi_norm'] = features_df['rsi'] / 100.0
        features_df['sma_ratio'] = features_df['sma20'] / features_df['sma50']
        features_df['atr_norm'] = features_df['atr'] / features_df['close']
        
        # Удаляем NaN значения
        features_df = features_df.dropna()
        
        return features_df
    
    def _create_sequences(self, data, labels=None):
        """Создает последовательности для LSTM"""
        sequences = []
        target_labels = []
        
        for i in range(self.lookback, len(data)):
            sequences.append(data[i-self.lookback:i])
            if labels is not None:
                target_labels.append(labels[i])
        
        if labels is not None:
            return np.array(sequences), np.array(target_labels)
        return np.array(sequences)
    
    def load_or_create_model(self, symbol):
        """Загружает существующую модель или создает новую"""
        self.model_path, self.scaler_path = self._get_model_paths(symbol)
        
        # Создаем директорию weights если её нет
        os.makedirs(self.model_dir, exist_ok=True)
        
        try:
            if os.path.exists(self.model_path) and os.path.exists(self.scaler_path):
                print(f"📥 Загрузка существующей модели для {symbol}")
                self.model = load_model(self.model_path)
                with open(self.scaler_path, 'rb') as f:
                    self.scaler = pickle.load(f)
                return True
            else:
                print(f"🆕 Создание новой модели для {symbol}")
                return False
        except Exception as e:
            print(f"❌ Ошибка загрузки модели для {symbol}: {e}")
            return False
    
    def train_model(self, df, symbol, epochs=5, is_initial=True):
        """Обучает модель на данных"""
        try:
            print(f"🧠 {'Первичное обучение' if is_initial else 'Дообучение'} модели {symbol} на {epochs} эпох")
            
            # Подготавливаем признаки
            features_df = self._prepare_features(df)
            
            if len(features_df) < self.lookback + 10:
                print(f"⚠️ Недостаточно данных для обучения {symbol}")
                return False
            
            # Создаем целевую переменную (будет расти цена или нет)
            future_returns = features_df['close'].pct_change(5).shift(-5)  # 5 периодов вперед
            labels = (future_returns > 0).astype(int).values
            
            # Масштабируем признаки
            feature_data = features_df.drop(['close'], axis=1).values  # Убираем close чтобы не было утечки
            scaled_features = self.scaler.fit_transform(feature_data)
            
            # Создаем последовательности
            X, y = self._create_sequences(scaled_features, labels)
            
            if len(X) == 0:
                print(f"⚠️ Не удалось создать последовательности для {symbol}")
                return False
            
            # Создаем или загружаем модель
            if self.model is None:
                self.model = self._create_model((X.shape[1], X.shape[2]))
            
            # Обучаем модель
            history = self.model.fit(
                X, y,
                epochs=epochs,
                batch_size=32,
                validation_split=0.1,
                verbose=1,
                shuffle=False
            )
            
            # Сохраняем модель и скейлер
            self.model.save(self.model_path)
            with open(self.scaler_path, 'wb') as f:
                pickle.dump(self.scaler, f)
            
            self.last_training_time = time.time()
            
            final_loss = history.history['loss'][-1]
            final_accuracy = history.history['accuracy'][-1]
            print(f"✅ Обучение {symbol} завершено. Loss: {final_loss:.4f}, Accuracy: {final_accuracy:.4f}")
            
            return True
            
        except Exception as e:
            print(f"❌ Ошибка обучения модели {symbol}: {e}")
            return False
    
    def predict_next(self, df):
        """Предсказывает вероятность роста цены"""
        try:
            if self.model is None:
                print(f"⚠️ Модель для {symbol if 'symbol' in locals() else 'unknown'} не загружена")
                return 0.5
            
            # Подготавливаем признаки
            features_df = self._prepare_features(df)
            
            if len(features_df) < self.lookback:
                return 0.5
            
            # Берем последние lookback записей
            recent_data = features_df.tail(self.lookback)
            feature_data = recent_data.drop(['close'], axis=1).values
            
            # Масштабируем признаки
            scaled_features = self.scaler.transform(feature_data)
            
            # Создаем последовательность
            sequence = scaled_features.reshape(1, self.lookback, -1)
            
            # Предсказываем
            prediction = self.model.predict(sequence, verbose=0)
            probability = float(prediction[0][0])
            
            return probability
            
        except Exception as e:
            print(f"❌ Ошибка предсказания: {e}")
            return 0.5
    
    def needs_retraining(self, retrain_interval_minutes=30):
        """Проверяет, нужно ли дообучение"""
        current_time = time.time()
        time_since_last_train = current_time - self.last_training_time
        return time_since_last_train >= (retrain_interval_minutes * 60)
