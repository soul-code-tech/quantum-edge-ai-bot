def train(self, df, symbol):
    try:
        data = self.prepare_features(df)
        
        # ✅ Проверка: хватает ли данных?
        if len(data) < self.lookback:  # 60
            raise ValueError(f"Недостаточно данных после обработки: {len(data)} строк, нужно {self.lookback}")
        
        X, y = self.create_sequences(data)
        if len(X) == 0:
            raise ValueError("Не удалось создать последовательности: слишком мало данных")

        X = X.reshape((X.shape[0], X.shape[1], 5))
        if self.model is None:
            self.build_model(input_shape=(X.shape[1], X.shape[2]))

        model_path = os.path.join(self.model_dir, f"{symbol}.keras")
        checkpoint = ModelCheckpoint(model_path, monitor='loss', save_best_only=True, mode='min')
        
        self.model.fit(X, y, epochs=10, batch_size=32, verbose=0, callbacks=[checkpoint])
        self.is_trained = True
        
        # ✅ Теперь действительно обучена
        print(f"✅ {symbol}: LSTM обучена и сохранена в {model_path}")

    except Exception as e:
        print(f"❌ Ошибка обучения LSTM для {symbol}: {e}")
        # ❌ Не ставим is_trained = True
        # ❌ Не считаем, что модель "обучена"
        # ❌ Не создаём пустой .keras файл
