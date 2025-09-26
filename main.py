# main.py — Quantum Edge AI Bot v5.0 (Цепочечный режим — ФИНАЛЬНАЯ ВЕРСИЯ)
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

# 9 пар — меньше нагрузки, больше диверсификации
SYMBOLS = [
    'BTC-USDT', 'ETH-USDT', 'SOL-USDT', 'BNB-USDT',
    'DOGE-USDT', 'AVAX-USDT', 'PENGU-USDT', 'SHIB-USDT', 'LINK-USDT'
]

# Параметры
RISK_PERCENT = 1.0
STOP_LOSS_PCT = 1.5
TAKE_PROFIT_PCT = 3.0
TRAILING_PCT = 1.0
LSTM_CONFIDENCE = 0.65
TIMEFRAME = '1h'
LOOKBACK = 200
SIGNAL_COOLDOWN = 3600
UPDATE_TRAILING_INTERVAL = 300
TEST_INTERVAL = 86400  # ✅ 24 часа в секундах

# ✅ ЦЕПОЧКА ОБУЧЕНИЯ: каждые 10 минут — одна пара
LSTM_TRAIN_DELAY = 600  # 10 минут в секундах — после сигнала
MONITORING_CYCLE = 60   # 60 секунд между циклами мониторинга

# Инициализация
lstm_models = {}
traders = {}

for symbol in SYMBOLS:
    lstm_models[symbol] = LSTMPredictor(lookback=60)
    traders[symbol] = BingXTrader(symbol=symbol, use_demo=True, leverage=10)

print("✅ [СТАРТ] Quantum Edge AI Bot запущен на 9 криптопарах")
print(f"📊 ПАРЫ: {', '.join(SYMBOLS)}")
print(f"🧠 LSTM: порог уверенности {LSTM_CONFIDENCE * 100}%")
print(f"💸 Риск: {RISK_PERCENT}% от депозита на сделку")
print(f"⛔ Стоп-лосс: {STOP_LOSS_PCT}% | 🎯 Тейк-профит: {TAKE_PROFIT_PCT}%")
print(f"📈 Трейлинг-стоп: {TRAILING_PCT}% от цены")
print(f"⏳ Кулдаун: {SIGNAL_COOLDOWN} сек. на пару")
print(f"🔄 LSTM обучение: по цепочке — каждые {LSTM_TRAIN_DELAY//60} минут после сигнала")
print(f"🔁 Мониторинг: {MONITORING_CYCLE} сек. между циклами")
print(f"🎯 Тестовый ордер: раз в {TEST_INTERVAL//3600} часов")

# Глобальные переменные
last_signal_time = {}
last_trailing_update = {}
last_test_order = 0
last_lstm_train_time = 0
last_lstm_next_symbol_index = 0  # Следующая пара для обучения
last_signal_sent = False  # Был ли отправлен сигнал для обучения
total_trades = 0

# ✅ НОВОЕ: При запуске — обучаем первую пару
print("\n🔄 [СТАРТ] Обучение первой пары при запуске: " + SYMBOLS[0])
df = get_bars(SYMBOLS[0], TIMEFRAME, LOOKBACK)
if df is not None and len(df) >= 100:
    df = calculate_strategy_signals(df, 60)
    try:
        lstm_models[SYMBOLS[0]].train(df)
        print(f"✅ {SYMBOLS[0]}: LSTM переобучена!")
        last_signal_sent = True  # ✅ Сигнал отправлен — теперь ждем 10 мин для следующей
        last_lstm_train_time = time.time()
        last_lstm_next_symbol_index = 1  # Готовим следующую
    except Exception as e:
        print(f"⚠️ {SYMBOLS[0]}: Ошибка обучения LSTM — {e}")
else:
    print(f"⚠️ {SYMBOLS[0]}: Недостаточно данных для обучения (df={len(df) if df is not None else 'None'})")
print("✅ Первая пара обучена. Ожидаем 10 минут для следующей.\n")

def run_strategy():
    global last_signal_time, last_trailing_update, last_test_order, total_trades, last_lstm_train_time, last_lstm_next_symbol_index, last_signal_sent
    while True:
        try:
            current_time = time.time()

            # ✅ 1. ОБУЧЕНИЕ — ПО ЦЕПОЧКЕ: ЖДЕМ 10 МИНУТ ПОСЛЕ СИГНАЛА
            if last_signal_sent and current_time - last_lstm_train_time >= LSTM_TRAIN_DELAY:
                symbol = SYMBOLS[last_lstm_next_symbol_index]
                print(f"\n🔄 [LSTM] Обучение: {symbol} (после сигнала от {SYMBOLS[(last_lstm_next_symbol_index - 1) % len(SYMBOLS)]})")

                df = get_bars(symbol, TIMEFRAME, LOOKBACK)
                if df is not None and len(df) >= 100:
                    df = calculate_strategy_signals(df, 60)
                    try:
                        lstm_models[symbol].train(df)
                        print(f"✅ {symbol}: LSTM переобучена!")
                        # ✅ Готовим следующий сигнал
                        last_signal_sent = True
                        last_lstm_train_time = current_time
                        last_lstm_next_symbol_index = (last_lstm_next_symbol_index + 1) % len(SYMBOLS)
                    except Exception as e:
                        print(f"⚠️ {symbol}: Ошибка обучения LSTM — {e}")
                        last_signal_sent = False  # Попробуем снова в следующем цикле
                else:
                    print(f"⚠️ {symbol}: Недостаточно данных для обучения (df={len(df) if df is not None else 'None'})")
                    last_signal_sent = False  # Попробуем снова в следующем цикле

            # ✅ 2. МОНИТОРИНГ И ТОРГОВЛЯ — КАЖДЫЕ 60 СЕКУНД (10 циклов между обучением)
            for i, symbol in enumerate(SYMBOLS):
                print(f"\n--- [{time.strftime('%H:%M:%S')}] {symbol} ---")
                
                time.sleep(10)  # Разбиваем цикл на 9 * 10 = 90 секунд — укладываемся в 10 минут

                df = get_bars(symbol, TIMEFRAME, LOOKBACK)
                if df is None or len(df) < 100:
                    print(f"❌ Недостаточно данных для {symbol}")
                    continue

                df = calculate_strategy_signals(df, 60)
                current_price = df['close'].iloc[-1]
                buy_signal = df['buy_signal'].iloc[-1]
                sell_signal = df['sell_signal'].iloc[-1]
                long_score = df['long_score'].iloc[-1]
                short_score = df['short_score'].iloc[-1]

                last_time = last_signal_time.get(symbol, 0)
                if current_time - last_time < SIGNAL_COOLDOWN:
                    print(f"⏳ Кулдаун: {symbol} — пропускаем")
                    continue

                lstm_prob = lstm_models[symbol].predict_next(df)
                lstm_confident = lstm_prob > LSTM_CONFIDENCE
                print(f"🧠 LSTM: {symbol} — {lstm_prob:.2%} → {'✅ ДОПУСТИМ' if lstm_confident else '❌ ОТКЛОНЕНО'}")

                strong_strategy = (buy_signal and long_score >= 5) or (sell_signal and short_score >= 5)
                if strong_strategy and lstm_confident:
                    side = 'buy' if buy_signal else 'sell'
                    print(f"🎯 [СИГНАЛ] {side.upper()} на {symbol}")

                    atr = df['atr'].iloc[-1]
                    equity = 100.0
                    risk_amount = equity * (RISK_PERCENT / 100)
                    stop_distance = atr * 1.5
                    amount = risk_amount / stop_distance if stop_distance > 0 else 0.001

                    # ✅ ПОЛУЧАЕМ МИНИМАЛЬНЫЙ РАЗМЕР ОРДЕРА
                    min_qty = traders[symbol].get_min_order_size()
                    if amount < min_qty:
                        amount = min_qty
                        print(f"⚠️ {symbol}: Размер ордера {amount:.6f} увеличен до минимального: {min_qty}")

                    print(f"📊 Размер позиции: {amount:.6f} {symbol.split('-')[0]} | ATR: {atr:.4f}")

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

            # ✅ 3. Обновление трейлинг-стопов — каждые 5 минут
            if current_time - last_trailing_update.get('global', 0) > UPDATE_TRAILING_INTERVAL:
                print("\n🔄 Обновление трейлинг-стопов для всех пар...")
                for symbol in SYMBOLS:
                    traders[symbol].update_trailing_stop()
                last_trailing_update['global'] = current_time

            # ✅ 4. ТЕСТОВЫЙ ОРДЕР — ТОЛЬКО РЫНОЧНЫЙ, БЕЗ TP/SL
            if current_time - last_test_order > TEST_INTERVAL:
                test_symbol = SYMBOLS[0]
                print(f"\n🎯 [ТЕСТ] ПРОВЕРКА СВЯЗИ: Принудительный MARKET BUY на {test_symbol} (раз в 24 часа)")
                traders[test_symbol].place_order(
                    side='buy',
                    amount=0.001,
                    stop_loss_percent=0,
                    take_profit_percent=0
                )
                last_test_order = current_time

            # ✅ 5. ЖДЕМ 60 СЕКУНД — ЭТО И ЕСТЬ ОСНОВНОЙ ЦИКЛ МОНИТОРИНГА
            print("\n💤 Ждём 60 секунд до следующего цикла мониторинга...")
            time.sleep(MONITORING_CYCLE)

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
    return "✅ Quantum Edge AI Bot is LIVE on 9 cryptos!", 200

@app.route('/health')
def health_check():
    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Flask сервер запущен на порту {port}")
    time.sleep(10)  # ✅ КРИТИЧЕСКИЙ ШАГ — ДАЁМ RENDER 10 СЕКУНД УВИДЕТЬ ПОРТ
    app.run(host='0.0.0.0', port=port)
