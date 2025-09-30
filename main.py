from flask import Flask
import threading
import time
import os
from data_fetcher import get_bars
from strategy import calculate_strategy_signals
from trader import BingXTrader
from lstm_model import LSTMPredictor

app = Flask(__name__)
_bot_started = False

SYMBOLS = [
    'BTC-USDT', 'ETH-USDT', 'SOL-USDT', 'BNB-USDT',
    'XRP-USDT', 'DOGE-USDT', 'TON-USDT', 'AVAX-USDT',
    'SHIB-USDT', 'LINK-USDT', 'PENGU-USDT'
]

RISK_PERCENT = 1.0
STOP_LOSS_PCT = 1.5
TAKE_PROFIT_PCT = 3.0
TRAILING_PCT = 1.0
LSTM_CONFIDENCE = 0.75
TIMEFRAME = '1h'
LOOKBACK = 200
SIGNAL_COOLDOWN = 3600
UPDATE_TRAILING_INTERVAL = 300
TEST_INTERVAL = 300
RETRAIN_INTERVAL_MINUTES = 30  # Интервал дообучения в минутах

# Глобальные переменные
lstm_models = {}
traders = {}
models_initially_trained = {}
last_signal_time = {}
last_trailing_update = {}
last_test_order = 0
last_retrain_time = 0
total_trades = 0

print("✅ [СТАРТ] Quantum Edge AI Bot запущен на 11 криптопарах")
print(f"📊 ПАРЫ: {', '.join(SYMBOLS)}")
print(f"🧠 LSTM: порог уверенности {LSTM_CONFIDENCE * 100}%")
print(f"💸 Риск: {RISK_PERCENT}% от депозита на сделку")
print(f"⛔ Стоп-лосс: {STOP_LOSS_PCT}% | 🎯 Тейк-профит: {TAKE_PROFIT_PCT}%")
print(f"📈 Трейлинг-стоп: {TRAILING_PCT}% от цены")
print(f"⏳ Кулдаун: {SIGNAL_COOLDOWN} сек. на пару")
print(f"🔄 Дообучение: каждые {RETRAIN_INTERVAL_MINUTES} минут на 2 эпохах")

def initialize_models():
    """Инициализирует модели для всех символов"""
    global lstm_models, traders, models_initially_trained
    
    print("\n🔄 Инициализация моделей и трейдеров...")
    
    for symbol in SYMBOLS:
        print(f"\n📊 Инициализация {symbol}...")
        
        # Создаем LSTM модель
        lstm_models[symbol] = LSTMPredictor(lookback=60, model_dir='weights')
        
        # Пытаемся загрузить существующую модель
        model_loaded = lstm_models[symbol].load_or_create_model(symbol)
        
        if not model_loaded:
            print(f"⚠️ Для {symbol} не найдена сохраненная модель, требуется первичное обучение")
            models_initially_trained[symbol] = False
        else:
            print(f"✅ Для {symbol} загружена сохраненная модель")
            models_initially_trained[symbol] = True
        
        # Создаем трейдера
        traders[symbol] = BingXTrader(symbol=symbol, use_demo=True, leverage=10)
    
    print(f"\n✅ Инициализация завершена. {len(SYMBOLS)} пар готовы к работе")

def perform_initial_training():
    """Выполняет первичное обучение для всех моделей"""
    global models_initially_trained, lstm_models
    
    print("\n🎓 Начало первичного обучения моделей...")
    print("⏳ Это может занять некоторое время (5 эпох на каждую пару)...")
    
    for symbol in SYMBOLS:
        if not models_initially_trained.get(symbol, False):
            print(f"\n🧠 Первичное обучение {symbol} (5 эпох)...")
            
            try:
                # Получаем данные для обучения (больше данных для первичного обучения)
                df = get_bars(symbol, TIMEFRAME, 500)  # 500 вместо 200 для лучшего обучения
                
                if df is None or len(df) < 100:
                    print(f"❌ Недостаточно данных для обучения {symbol}")
                    continue
                
                # Добавляем технические индикаторы
                df = calculate_strategy_signals(df, 60)
                
                # Обучаем модель на 5 эпох
                success = lstm_models[symbol].train_model(
                    df, 
                    symbol, 
                    epochs=5, 
                    is_initial=True
                )
                
                if success:
                    models_initially_trained[symbol] = True
                    print(f"✅ Первичное обучение {symbol} завершено успешно")
                else:
                    print(f"❌ Ошибка при обучении {symbol}")
                    
            except Exception as e:
                print(f"❌ Критическая ошибка обучения {symbol}: {e}")
    
    print("\n✅ Первичное обучение завершено!")
    
    # Считаем сколько моделей обучено
    trained_count = sum(1 for trained in models_initially_trained.values() if trained)
    print(f"📊 Обучено моделей: {trained_count}/{len(SYMBOLS)}")

def perform_retraining():
    """Выполняет дообучение моделей каждые 30 минут"""
    global lstm_models, last_retrain_time
    
    current_time = time.time()
    
    # Проверяем, прошло ли 30 минут с последнего дообучения
    if current_time - last_retrain_time < (RETRAIN_INTERVAL_MINUTES * 60):
        return
    
    print(f"\n🔄 Начало дообучения моделей ({RETRAIN_INTERVAL_MINUTES} минут прошло)...")
    
    retrained_count = 0
    
    for symbol in SYMBOLS:
        try:
            # Проверяем, нужно ли дообучение для конкретной модели
            if lstm_models[symbol].needs_retraining(RETRAIN_INTERVAL_MINUTES):
                print(f"\n🧠 Дообучение {symbol} (2 эпохи)...")
                
                # Получаем свежие данные
                df = get_bars(symbol, TIMEFRAME, LOOKBACK)
                
                if df is None or len(df) < 100:
                    print(f"❌ Недостаточно данных для дообучения {symbol}")
                    continue
                
                # Добавляем технические индикаторы
                df = calculate_strategy_signals(df, 60)
                
                # Дообучаем модель на 2 эпохи
                success = lstm_models[symbol].train_model(
                    df,
                    symbol,
                    epochs=2,  # Дообучение на 2 эпохи
                    is_initial=False
                )
                
                if success:
                    retrained_count += 1
                    print(f"✅ Дообучение {symbol} завершено")
                else:
                    print(f"❌ Ошибка дообучения {symbol}")
            else:
                print(f"⏳ {symbol}: Дообучение не требуется")
                
        except Exception as e:
            print(f"❌ Критическая ошибка дообучения {symbol}: {e}")
    
    last_retrain_time = current_time
    
    if retrained_count > 0:
        print(f"\n✅ Дообучение завершено! Обновлено моделей: {retrained_count}")
    else:
        print(f"\n⏳ Ни одна модель не требовала дообучения")

def run_strategy():
    global last_signal_time, last_trailing_update, last_test_order, total_trades, last_retrain_time
    
    # Инициализируем модели при первом запуске
    initialize_models()
    
    # Выполняем первичное обучение
    perform_initial_training()
    
    # Устанавливаем время последнего дообучения
    last_retrain_time = time.time()
    
    print("\n🚀 Бот полностью запущен и готов к торговле!")
    print("📊 Начинаем основной цикл стратегии...")
    
    while True:
        try:
            current_time = time.time()
            
            # Выполняем дообучение каждые 30 минут
            perform_retraining()
            
            for symbol in SYMBOLS:
                print(f"\n--- [{time.strftime('%H:%M:%S')}] {symbol} ---")
                
                # Получаем данные
                df = get_bars(symbol, TIMEFRAME, LOOKBACK)
                if df is None or len(df) < 100:
                    print(f"❌ Недостаточно данных для {symbol}")
                    continue
                
                # Вычисляем сигналы стратегии
                df = calculate_strategy_signals(df, 60)
                current_price = df['close'].iloc[-1]
                buy_signal = df['buy_signal'].iloc[-1]
                sell_signal = df['sell_signal'].iloc[-1]
                long_score = df['long_score'].iloc[-1]
                short_score = df['short_score'].iloc[-1]
                
                # Проверяем кулдаун
                last_time = last_signal_time.get(symbol, 0)
                if current_time - last_time < SIGNAL_COOLDOWN:
                    print(f"⏳ Кулдаун: {symbol} — пропускаем")
                    continue
                
                # Получаем предсказание LSTM
                lstm_prob = lstm_models[symbol].predict_next(df)
                lstm_confident = lstm_prob > LSTM_CONFIDENCE
                
                print(f"🧠 LSTM: {symbol} — {lstm_prob:.2%} → {'✅ ДОПУСТИМ' if lstm_confident else '❌ ОТКЛОНЕНО'}")
                
                # Определяем сильный сигнал стратегии
                strong_strategy = (buy_signal and long_score >= 5) or (sell_signal and short_score >= 5)
                
                if strong_strategy and lstm_confident:
                    side = 'buy' if buy_signal else 'sell'
                    print(f"🎯 [СИГНАЛ] {side.upper()} на {symbol}")
                    
                    # Рассчитываем размер позиции
                    atr = df['atr'].iloc[-1]
                    equity = 100.0  # Заглушка для баланса
                    risk_amount = equity * (RISK_PERCENT / 100)
                    stop_distance = atr * 1.5
                    amount = risk_amount / stop_distance if stop_distance > 0 else 0.001
                    
                    if amount < 0.001:
                        amount = 0.001
                    
                    print(f"📊 Размер позиции: {amount:.6f} {symbol.split('-')[0]} | ATR: {atr:.4f}")
                    
                    # Отправляем ордер
                    order = traders[symbol].place_order(
                        side=side,
                        amount=amount,
                        stop_loss_percent=STOP_LOSS_PCT,
                        take_profit_percent=TAKE_PROFIT_PCT
                    )
                    
                    if order:
                        print(f"✅ УСПЕХ! Ордер {side} на {symbol} отправлен.")
                        total_trades += 1
                        last_signal_time[symbol] = current_time
                    else:
                        print(f"❌ ОШИБКА: Ордер не отправлен на {symbol}")
                else:
                    if buy_signal or sell_signal:
                        print(f"⚠️ {symbol}: Сигнал есть, но не достаточно сильный (score={long_score if buy_signal else short_score}) или LSTM не уверен ({lstm_prob:.2%}) — пропускаем.")
            
            # Обновляем трейлинг-стопы каждые 5 минут
            if current_time - last_trailing_update.get('global', 0) > UPDATE_TRAILING_INTERVAL:
                print("\n🔄 Обновление трейлинг-стопов для всех пар...")
                for symbol in SYMBOLS:
                    traders[symbol].update_trailing_stop()
                last_trailing_update['global'] = current_time
            
            # Тестовый ордер каждые 5 минут
            if current_time - last_test_order > TEST_INTERVAL:
                test_symbol = SYMBOLS[0]  # BTC-USDT
                print(f"\n🎯 [ТЕСТ] Принудительный BUY на {test_symbol} для проверки связи...")
                traders[test_symbol].place_order(
                    side='buy',
                    amount=0.001,
                    stop_loss_percent=STOP_LOSS_PCT,
                    take_profit_percent=TAKE_PROFIT_PCT
                )
                last_test_order = current_time
            
            print("\n💤 Ждём 60 секунд до следующего цикла...")
            time.sleep(60)
            
        except Exception as e:
            print(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {type(e).__name__}: {str(e)}")
            print("⏳ Перезапуск цикла через 60 секунд...")
            time.sleep(60)

@app.before_request
def start_bot_once():
    global _bot_started
    if not _bot_started:
        thread = threading.Thread(target=run_strategy, daemon=True)
        thread.start()
        print("🚀 [СИСТЕМА] Фоновый торговый бот успешно запущен!")
        _bot_started = True

@app.route('/')
def wake_up():
    trained_count = sum(1 for trained in models_initially_trained.values() if trained)
    return f"✅ Quantum Edge AI Bot is LIVE on {len(SYMBOLS)} cryptos!<br>📊 Trained models: {trained_count}/{len(SYMBOLS)}<br>🔄 Retraining every {RETRAIN_INTERVAL_MINUTES} min", 200

@app.route('/health')
def health_check():
    return "OK", 200

@app.route('/status')
def status():
    """Детальный статус бота"""
    trained_count = sum(1 for trained in models_initially_trained.values() if trained)
    status_info = {
        'status': 'running',
        'symbols': len(SYMBOLS),
        'trained_models': f"{trained_count}/{len(SYMBOLS)}",
        'total_trades': total_trades,
        'retrain_interval_minutes': RETRAIN_INTERVAL_MINUTES,
        'last_retrain_time': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(last_retrain_time)) if last_retrain_time > 0 else 'never'
    }
    
    return str(status_info), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Flask сервер запущен на порту {port}")
    app.run(host='0.0.0.0', port=port)
