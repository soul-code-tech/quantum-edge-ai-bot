#!/usr/bin/env python3
"""
Тестовый скрипт для проверки работоспособности Quantum Edge AI Bot
"""

import os
import sys
import time
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

def test_imports():
    """Тестируем импорты всех модулей"""
    print("🧪 Тестирование импортов модулей...")
    
    try:
        import ccxt
        print("✅ ccxt импортирован")
    except ImportError as e:
        print(f"❌ Ошибка импорта ccxt: {e}")
        return False
    
    try:
        import pandas as pd
        print("✅ pandas импортирован")
    except ImportError as e:
        print(f"❌ Ошибка импорта pandas: {e}")
        return False
    
    try:
        import numpy as np
        print("✅ numpy импортирован")
    except ImportError as e:
        print(f"❌ Ошибка импорта numpy: {e}")
        return False
    
    try:
        import tensorflow as tf
        print(f"✅ tensorflow импортирован (версия: {tf.__version__})")
        print(f"📊 Доступные устройства: {tf.config.list_physical_devices()}")
    except ImportError as e:
        print(f"❌ Ошибка импорта tensorflow: {e}")
        return False
    
    try:
        from ta.momentum import RSIIndicator
        from ta.volatility import AverageTrueRange
        from ta.trend import SMAIndicator
        print("✅ ta (technical analysis) импортирован")
    except ImportError as e:
        print(f"❌ Ошибка импорта ta: {e}")
        return False
    
    try:
        from flask import Flask
        print("✅ flask импортирован")
    except ImportError as e:
        print(f"❌ Ошибка импорта flask: {e}")
        return False
    
    return True

def test_environment():
    """Тестирование переменных окружения"""
    print("\n🧪 Тестирование переменных окружения...")
    
    api_key = os.getenv('BINGX_API_KEY')
    secret_key = os.getenv('BINGX_SECRET_KEY')
    
    if api_key:
        print("✅ BINGX_API_KEY установлен")
    else:
        print("❌ BINGX_API_KEY не установлен")
        return False
    
    if secret_key:
        print("✅ BINGX_SECRET_KEY установлен")
    else:
        print("❌ BINGX_SECRET_KEY не установлен")
        return False
    
    return True

def test_modules():
    """Тестирование пользовательских модулей"""
    print("\n🧪 Тестирование пользовательских модулей...")
    
    try:
        from data_fetcher import get_bars
        print("✅ data_fetcher импортирован")
    except ImportError as e:
        print(f"❌ Ошибка импорта data_fetcher: {e}")
        return False
    
    try:
        from strategy import calculate_strategy_signals
        print("✅ strategy импортирован")
    except ImportError as e:
        print(f"❌ Ошибка импорта strategy: {e}")
        return False
    
    try:
        from trader import BingXTrader
        print("✅ trader импортирован")
    except ImportError as e:
        print(f"❌ Ошибка импорта trader: {e}")
        return False
    
    try:
        from lstm_model import LSTMPredictor
        print("✅ lstm_model импортирован")
    except ImportError as e:
        print(f"❌ Ошибка импорта lstm_model: {e}")
        return False
    
    return True

def test_data_fetching():
    """Тестирование получения данных"""
    print("\n🧪 Тестирование получения данных с биржи...")
    
    try:
        from data_fetcher import get_bars
        
        # Тестируем получение данных для BTC-USDT
        df = get_bars('BTC-USDT', '1h', 100)
        
        if df is not None and len(df) > 0:
            print(f"✅ Данные получены успешно. Размер: {len(df)} записей")
            print(f"📊 Колонки: {list(df.columns)}")
            print(f"📈 Последняя цена: {df['close'].iloc[-1]:.2f}")
            return True
        else:
            print("❌ Не удалось получить данные")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка при получении данных: {e}")
        return False

def test_strategy():
    """Тестирование стратегии"""
    print("\n🧪 Тестирование стратегии...")
    
    try:
        from data_fetcher import get_bars
        from strategy import calculate_strategy_signals
        
        # Получаем данные
        df = get_bars('BTC-USDT', '1h', 200)
        
        if df is None:
            print("❌ Нет данных для тестирования стратегии")
            return False
        
        # Применяем стратегию
        df_with_signals = calculate_strategy_signals(df, 60)
        
        # Проверяем наличие сигналов
        buy_signals = df_with_signals['buy_signal'].sum()
        sell_signals = df_with_signals['sell_signal'].sum()
        
        print(f"✅ Стратегия применена успешно")
        print(f"📊 Buy сигналов: {buy_signals}")
        print(f)        print(f"📊 Sell сигналов: {sell_signals}")
        print(f"📈 Индикаторы: {['rsi', 'sma20', 'sma50', 'atr', 'trend_score', 'long_score', 'short_score']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при тестировании стратегии: {e}")
        return False

def test_lstm_model():
    """Тестирование LSTM модели"""
    print("\n🧪 Тестирование LSTM модели...")
    
    try:
        from data_fetcher import get_bars
        from strategy import calculate_strategy_signals
        from lstm_model import LSTMPredictor
        
        # Создаем тестовую модель
        model = LSTMPredictor(lookback=60, model_dir='test_weights')
        
        # Получаем данные
        df = get_bars('BTC-USDT', '1h', 200)
        df = calculate_strategy_signals(df, 60)
        
        # Тестируем предсказание
        prediction = model.predict_next(df)
        
        print(f"✅ LSTM модель работает")
        print(f"🧠 Предсказание: {prediction:.2%}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при тестировании LSTM модели: {e}")
        return False

def test_trader():
    """Тестирование трейдера"""
    print("\n🧪 Тестирование трейдера...")
    
    try:
        from trader import BingXTrader
        
        # Создаем тестового трейдера в демо-режиме
        trader = BingXTrader(symbol='BTC-USDT', use_demo=True, leverage=10)
        
        print("✅ Трейдер создан успешно")
        print(f"📊 Символ: {trader.symbol}")
        print(f"🔧 Плечо: {trader.leverage}x")
        print(f"🎯 Демо-режим: {trader.use_demo}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при тестировании трейдера: {e}")
        return False

def test_weights_directory():
    """Тестирование директории weights"""
    print("\n🧪 Тестирование директории weights...")
    
    weights_dir = 'weights'
    
    if os.path.exists(weights_dir):
        print("✅ Директория weights существует")
    else:
        try:
            os.makedirs(weights_dir)
            print("✅ Директория weights создана")
        except Exception as e:
            print(f"❌ Ошибка создания директории weights: {e}")
            return False
    
    # Проверяем права на запись
    test_file = os.path.join(weights_dir, 'test.txt')
    try:
        with open(test_file, 'w') as f:
            f.write('test')
        os.remove(test_file)
        print("✅ Права на запись в директории weights есть")
        return True
    except Exception as e:
        print(f"❌ Ошибка проверки прав на запись: {e}")
        return False

def main():
    """Главная функция тестирования"""
    print("🚀 Quantum Edge AI Bot - Тестирование")
    print("=" * 50)
    
    all_tests_passed = True
    
    # Последовательно запускаем все тесты
    tests = [
        ("Импорты", test_imports),
        ("Переменные окружения", test_environment),
        ("Модули", test_modules),
        ("Директория weights", test_weights_directory),
        ("Получение данных", test_data_fetching),
        ("Стратегия", test_strategy),
        ("LSTM модель", test_lstm_model),
        ("Трейдер", test_trader),
    ]
    
    for test_name, test_func in tests:
        if not test_func():
            all_tests_passed = False
            print(f"\n❌ Тест '{test_name}' провален!")
            break
        else:
            print(f"✅ Тест '{test_name}' пройден")
    
    print("\n" + "=" * 50)
    
    if all_tests_passed:
        print("🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
        print("✅ Бот готов к запуску")
        print("\nДля запуска выполните:")
        print("python main.py")
    else:
        print("❌ НЕКОТОРЫЕ ТЕСТЫ ПРОВАЛЕНЫ!")
        print("🔧 Исправьте ошибки перед запуском")
        sys.exit(1)

if __name__ == "__main__":
    main()
