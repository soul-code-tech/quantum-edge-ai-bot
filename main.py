# main.py — фрагмент start_all()

def start_all():
    logging.info("=== СТАРТ start_all() ===")
    
    # Шаг 1: Скачиваем веса из GitHub (если есть)
    download_weights()  # → /tmp/lstm_weights/

    # Шаг 2: Пытаемся загрузить каждую модель
    trained_count = 0
    for s in SYMBOLS:
        model = load_model(s)
        if model:
            lstm_models[s] = model
            logging.info(f"✅ Модель {s} загружена из GitHub")
            trained_count += 1
        else:
            logging.warning(f"⚠️ Модель {s} отсутствует — будет обучена")

    # Шаг 3: Если ни одна модель не загружена — обучаем последовательно
    if trained_count == 0:
        logging.info("🧠 Нет готовых моделей — начинаем первичное обучение (последовательно)...")
        for s in SYMBOLS:
            if train_one(s, epochs=5):  # ← обучает и сохраняет в /tmp
                lstm_models[s].is_trained = True
                logging.info(f"✅ {s} обучена — начинаем торговлю")
            time.sleep(5)  # пауза между парами
    else:
        # Обучаем только недостающие
        missing = [s for s in SYMBOLS if not lstm_models[s].is_trained]
        for s in missing:
            if train_one(s, epochs=5):
                lstm_models[s].is_trained = True
                logging.info(f"✅ {s} обучена — начинаем торговлю")
            time.sleep(5)

    # Шаг 4: Запускаем торговлю (уже работает для всех is_trained=True)
    threading.Thread(target=run_strategy, daemon=True).start()

    # Шаг 5: Фоновое дообучение (каждый час, 2 эпохи)
    def hourly_retrain():
        while True:
            for s in SYMBOLS:
                if lstm_models[s].is_trained:
                    logging.info(f"🔁 Дообучение {s} (2 эпохи)...")
                    train_one(s, epochs=2)
                time.sleep(10)  # пауза между парами
            time.sleep(3600)  # ждём 1 час

    threading.Thread(target=hourly_retrain, daemon=True).start()

    # Остальное...
    start_position_monitor(traders, SYMBOLS)
    threading.Thread(target=keep_alive, daemon=True).start()
    logging.info("🚀 Quantum Edge AI Bot полностью запущен!")
