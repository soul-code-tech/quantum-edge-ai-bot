# main.py — Quantum Edge AI Bot v3.7 (Render-Optimized — ФИНАЛЬНАЯ ВЕРСИЯ)
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
    'SOL-USDT', 'BNB-USDT', 'AVAX-USDT', 'BTC-USDT', 'ETH-USDT', 
    'DOGE-USDT', 'PENGU-USDT', 'SHIB-USDT', 'LINK-USDT'
]

RISK_PERCENT = 1.0
STOP_LOSS_PCT = 1.5
TAKE_PROFIT_PCT = 3.0
TRAILING_PCT = 1.0
LSTM_CONFIDENCE = 0.65
TIMEFRAME = '1h'
LOOKBACK = 200
SIGNAL_COOLDOWN = 3600
UPDATE_TRAILING_INTERVAL = 300
TEST_INTERVAL = 86400
LSTM_TRAIN_INTERVAL = 2400  # 40 минут

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
print(f"🔄 LSTM обучение: каждые {LSTM_TRAIN_INTERVAL//60} минут (по одной паре)")
print(f"🎯 Тестовый ордер: раз в {TEST_INTERVAL//3600} часов")

last_signal_time = {}
last_trailing_update = {}
last_test_order = 0
last_lstm_train_time = 0
last_lstm_next_symbol_index = 0
total_trades = 0

# ✅ ИСПРАВЛЕНО: ПРИ ЗАПУСКЕ — ОБУЧАЕМ ТОЛЬКО ПЕРВУЮ ПАРУ
first_symbol = SYMBOLS[0]
print(f"\n🔄 [СТАРТ] Обучение первой пары при запуске: {first_symbol}")
df = get_bars(first_symbol, TIMEFRAME, LOOKBACK)
if df is not None and len(df) >= 100:
    df = calculate_strategy_signals(df, 60)
    try:
        lstm_models[first_symbol].train(df)
        print(f"✅ {first_symbol}: LSTM переобучена!")
    except Exception as e:
        print(f"⚠️ {first_symbol}: Ошибка обучения LSTM — {e}")
else:
    print(f"⚠️ {first_symbol}: Недостаточно данных для обучения (df={len(df) if df is not None else 'None'})")
print("✅ Первая пара обучена при запуске. Остальные — по расписанию.\n")

def run_strategy():
    global last_signal_time, last_trailing_update, last_test_order, total_trades, last_lstm_train_time, last_lstm_next_symbol_index
    while True:
        try:
            current_time = time.time()

            # ✅ 1. Обучение LSTM — КАЖДЫЕ 40 МИНУТ — ПО ОДНОЙ ПАРЕ
            if current_time - last_lstm_train_time >= LSTM_TRAIN_INTERVAL:
                symbol = SYMBOLS[last_lstm_next_symbol_index]
                print(f"\n🔄 [LSTM] Обучение: {symbol} (шаг {last_lstm_next_symbol_index + 1}/{len(SYMBOLS)})")

                df = get_bars(symbol, TIMEFRAME, LOOKBACK)
                if df is not None and len(df) >= 100:
                    df = calculate_strategy_signals(df, 60)
                    try:
                        lstm_models[symbol].train(df)
                        print(f"✅ {symbol}: LSTM переобучена!")
                    except Exception as e:
                        print(f"⚠️ {symbol}: Ошибка обучения LSTM — {e}")
                else:
                    print(f"⚠️ {symbol}: Недостаточно данных для обучения (df={len(df) if df is not None else 'None'})")

                last_lstm_next_symbol_index = (last_lstm_next_symbol_index + 1) % len(SYMBOLS)
                last_lstm_train_time = current_time

            # ✅ 2. Анализ каждой пары с задержкой 10 сек
            for i, symbol in enumerate(SYMBOLS):
                print(f"\n--- [{time.strftime('%H:%M:%S')}] {symbol} ---")
                
                time.sleep(10)

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
                    if amount < 0.001: amount = 0.001

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
    return "✅ Quantum Edge AI Bot is LIVE on 9 cryptos!", 200

@app.route('/health')
def health_check():
    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Flask сервер запущен на порту {port}")
    time.sleep(10)  # ✅ КРИТИЧЕСКИЙ ШАГ — ДАЁМ RENDER 10 СЕКУНД УВИДЕТЬ ПОРТ
    app.run(host='0.0.0.0', port=port)
