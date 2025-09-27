from flask import Flask
import threading
import time
import os
import requests
from data_fetcher import get_bars
from strategy import calculate_strategy_signals
from trader import BingXTrader
from lstm_model import LSTMPredictor
from trainer import initial_train_all, sequential_trainer, load_model

app = Flask(__name__)

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

# --- ИНИЦИАЛИЗАЦИЯ БЕЗ ОБУЧЕНИЯ ---
lstm_models = {}
traders = {}

print("✅ [СТАРТ] Quantum Edge AI Bot запущен на", len(SYMBOLS), "парах")

last_signal_time = {}
last_trailing_update = {}
total_trades = 0

def keep_alive():
    host = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
    if not host:
        return
    url = f"https://{host}/health"
    while True:
        try:
            requests.get(url, timeout=10)
        except:
            pass
        time.sleep(120)

def run_strategy():
    global last_signal_time, last_trailing_update, total_trades

    # --- ЗАГРУЗКА МОДЕЛЕЙ И ТРЕЙДЕРОВ ---
    print("🔄 Загружаем модели и инициализируем трейдеров...")
    for symbol in SYMBOLS:
        model = load_model(symbol)
        if model:
            lstm_models[symbol] = model
            print(f"✅ Модель для {symbol} загружена.")
        else:
            print(f"❌ Модель для {symbol} не найдена. Используем пустую, но обучение должно было пройти.")
            lstm_models[symbol] = LSTMPredictor()
    
    for symbol in SYMBOLS:
        traders[symbol] = BingXTrader(symbol=symbol, use_demo=False, leverage=10)  # ! use_demo=False

    print("🚀 Торговый цикл запущен.")

    while True:
        try:
            current_time = time.time()
            for symbol in SYMBOLS:
                print(f"\n--- [{time.strftime('%H:%M:%S')}] {symbol} ---")
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
                    print(f"⏳ Кулдаун: {symbol} – пропускаем")
                    continue

                # --- ПРОВЕРКА ОБУЧЕННОСТИ МОДЕЛИ ---
                model = lstm_models[symbol]
                if not model.is_trained:
                    print(f"⚠️ Модель для {symbol} не обучена. Пропускаем.")
                    continue

                lstm_prob = model.predict_next(df)
                lstm_confident = lstm_prob > LSTM_CONFIDENCE
                print(f"🧠 LSTM: {symbol} – {lstm_prob:.2%} → {'✅ ДОПУСТИМ' if lstm_confident else '❌ ОТКЛОНЕНО'}")

                strong_strategy = (buy_signal and long_score >= 5) or (sell_signal and short_score >= 5)
                if strong_strategy and lstm_confident:
                    side = 'buy' if buy_signal else 'sell'
                    print(f"🎯 [СИГНАЛ] {side.upper()} на {symbol}")
                    atr = df['atr'].iloc[-1]
                    equity = 100.0
                    risk_amount = equity * (RISK_PERCENT / 100)
                    stop_distance = atr * 1.5
                    amount = risk_amount / stop_distance if stop_distance > 0 else 0.001
                    if amount < 0.001:
                        amount = 0.001
                    print(f"📊 Размер позиции: {amount:.6f} {symbol.split('-')[0]} | ATR: {atr:.4f}")
                    order = traders[symbol].place_order(
                        side=side,
                        amount=amount,
                        stop_loss_percent=STOP_LOSS_PCT,
                        take_profit_percent=TAKE_PROFIT_PCT
                    )
                    if order:
                        print(f"✅ Ордер {side} на {symbol} отправлен.")
                        total_trades += 1
                        last_signal_time[symbol] = current_time
                    else:
                        print(f"❌ Ордер не отправлен на {symbol}")
                else:
                    if buy_signal or sell_signal:
                        print(f"⚠️ {symbol}: сигнал есть, но не достаточно сильный (score={long_score if buy_signal else short_score}) или LSTM не уверен ({lstm_prob:.2%}) – пропускаем.")

            if current_time - last_trailing_update.get('global', 0) > UPDATE_TRAILING_INTERVAL:
                print("\n🔄 Обновление трейлинг-стопов для всех пар...")
                for symbol in SYMBOLS:
                    traders[symbol].update_trailing_stop()
                last_trailing_update['global'] = current_time

            print("\n💤 Ждём 60 секунд до следующего цикла...")
            time.sleep(60)
        except Exception as e:
            print(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {type(e).__name__}: {str(e)}")
            print("⏳ Перезапуск цикла через 60 секунд...")
            time.sleep(60)

def start_all():
    # 1. Последовательное первичное обучение (один раз)
    initial_train_all(SYMBOLS)
    # 2. Запуск фоновых задач: торговля, дообучение, keep-alive
    threading.Thread(target=run_strategy, daemon=True).start()
    threading.Thread(target=sequential_trainer, args=(SYMBOLS, 600), daemon=True).start()
    threading.Thread(target=keep_alive, daemon=True).start()
    print("🚀 trading + sequential 10-min retraining + keep-alive loops started")

@app.route('/')
def wake_up():
    return f"✅ Quantum Edge AI Bot is LIVE on {len(SYMBOLS)} cryptos!", 200

@app.route('/health')
def health_check():
    return "OK", 200

if __name__ == "__main__":
    # Запускаем обучение и фоновые задачи в отдельном потоке
    threading.Thread(target=start_all, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Flask server starting on port {port}")
    app.run(host='0.0.0.0', port=port)
