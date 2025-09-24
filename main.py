# main.py — ФИНАЛЬНАЯ ВЕРСИЯ: 10 КРИПТОПАР + LSTM + ТРЕЙЛИНГ-СТОП + РИСК-МЕНЕДЖМЕНТ
from flask import Flask
import time
import os
from data_fetcher import get_bars
from strategy import calculate_strategy_signals
from trader import BingXTrader
from lstm_model import LSTMPredictor

app = Flask(__name__)
_bot_started = False

# 📊 СПИСОК ПАР — ДОБАВЬ/УБЕРИ ПАРЫ ПО ЖЕЛАНИЮ
SYMBOLS = [
    'BTC-USDT', 'ETH-USDT', 'SOL-USDT', 'BNB-USDT',
    'XRP-USDT', 'DOGE-USDT', 'TON-USDT', 'AVAX-USDT',
    'SHIB-USDT', 'LINK-USDT', 'PENGU-USDT'
]

# Параметры торговли
RISK_PERCENT = 1.0          # Риск 1% от депозита на сделку
STOP_LOSS_PCT = 1.5         # Стоп-лосс: 1.5% от цены входа
TAKE_PROFIT_PCT = 3.0       # Тейк-профит: 3% от цены входа
TRAILING_PCT = 1.0          # Трейлинг-стоп: отслеживает цену с отставанием 1%
LSTM_CONFIDENCE = 0.65      # LSTM должен быть уверен на 65%+
TIMEFRAME = '1h'
LOOKBACK = 200              # Свечей для LSTM
SIGNAL_COOLDOWN = 3600      # 1 час между сигналами на одну пару
TEST_INTERVAL = 300         # Тестовый ордер каждые 5 минут
UPDATE_TRAILING_INTERVAL = 300  # Обновление трейлинга каждые 5 минут

# Инициализация моделей и трейдеров
lstm_models = {}
traders = {}

for symbol in SYMBOLS:
    lstm_models[symbol] = LSTMPredictor(lookback=60)
    traders[symbol] = BingXTrader(symbol=symbol, use_demo=True)

print("✅ [СТАРТ] Quantum Edge AI Bot запущен на 10 криптопарах")
print(f"📊 ПАРЫ: {', '.join(SYMBOLS)}")
print(f"🧠 LSTM: порог уверенности {LSTM_CONFIDENCE * 100}%")
print(f"💸 Риск: {RISK_PERCENT}% от депозита на сделку")
print(f"⛔ Стоп-лосс: {STOP_LOSS_PCT}% | 🎯 Тейк-профит: {TAKE_PROFIT_PCT}%")
print(f"📈 Трейлинг-стоп: {TRAILING_PCT}% от цены")
print(f"⏳ Кулдаун: {SIGNAL_COOLDOWN} сек. на пару")

# --- ГЛОБАЛЬНЫЕ СТАТИСТИКИ ---
last_signal_time = {}     # Время последнего сигнала по паре
last_trailing_update = {} # Время последнего трейлинга по паре
last_test_order = 0       # Время последнего тестового ордера
total_trades = 0          # Общее количество сделок

def run_strategy():
    global last_signal_time, last_trailing_update, last_test_order, total_trades

    while True:
        try:
            current_time = time.time()

            # 🔁 Обрабатываем каждую пару по очереди
            for symbol in SYMBOLS:
                print(f"\n--- [{time.strftime('%H:%M:%S')}] {symbol} ---")

                # Получаем данные
                df = get_bars(symbol, TIMEFRAME, LOOKBACK)
                if df is None or len(df) < 100:
                    print(f"❌ Недостаточно данных для {symbol}")
                    continue

                # Рассчитываем стратегию
                df = calculate_strategy_signals(df, 60)
                current_price = df['close'].iloc[-1]
                buy_signal = df['buy_signal'].iloc[-1]
                sell_signal = df['sell_signal'].iloc[-1]
                long_score = df['long_score'].iloc[-1]
                short_score = df['short_score'].iloc[-1]

                # Проверяем, не было ли сигнала недавно
                last_time = last_signal_time.get(symbol, 0)
                if current_time - last_time < SIGNAL_COOLDOWN:
                    print(f"⏳ Кулдаун: {symbol} — пропускаем")
                    continue

                # ✅ LSTM-фильтр
                lstm_prob = lstm_models[symbol].predict_next(df)
                lstm_confident = lstm_prob > LSTM_CONFIDENCE
                print(f"🧠 LSTM: {symbol} — {lstm_prob:.2%} → {'✅ ДОПУСТИМ' if lstm_confident else '❌ ОТКЛОНЕНО'}")

                # ✅ СИЛЬНЫЙ СИГНАЛ: стратегия + LSTM
                strong_strategy = (buy_signal and long_score >= 5) or (sell_signal and short_score >= 5)

                if strong_strategy and lstm_confident:
                    side = 'buy' if buy_signal else 'sell'
                    print(f"🎯 [СИГНАЛ] {side.upper()} на {symbol} — сильный сигнал + LSTM уверен")

                    # 💰 РИСК-МЕНЕДЖМЕНТ
                    atr = df['atr'].iloc[-1]
                    equity = 100.0  # Можно заменить на реальный депозит через API
                    risk_amount = equity * (RISK_PERCENT / 100)
                    stop_distance = atr * 1.5
                    amount = risk_amount / stop_distance if stop_distance > 0 else 0.001

                    if amount < 0.001:
                        amount = 0.001

                    print(f"📊 Размер позиции: {amount:.6f} {symbol.split('-')[0]} | ATR: {atr:.4f}")

                    # Открываем ордер
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

            # ✅ ТРЕЙЛИНГ-СТОП — обновляем каждые 5 минут для всех пар
            if current_time - last_trailing_update.get('global', 0) > UPDATE_TRAILING_INTERVAL:
                print("\n🔄 Обновление трейлинг-стопов для всех пар...")
                for symbol in SYMBOLS:
                    traders[symbol].update_trailing_stop()
                last_trailing_update['global'] = current_time

            # ✅ ПАУЗА — 60 секунд между циклами
            print("\n💤 Ждём 60 секунд до следующего цикла...")
            time.sleep(60)

        except Exception as e:
            print(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {type(e).__name__}: {str(e)}")
            print("⏳ Перезапуск цикла через 60 секунд...")
            time.sleep(60)
