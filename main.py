from flask import Flask
import threading
import time
import os
from data_fetcher import get_bars
from strategy import calculate_strategy_signals
from trader import BingXTrader
from lstm_model import LSTMPredictor
import ccxt

app = Flask(__name__)
_bot_started = False

SYMBOLS = [
    'BTC-USDT', 'ETH-USDT', 'SOL-USDT', 'BNB-USDT',
    'XRP-USDT', 'DOGE-USDT', 'AVAX-USDT', 'SHIB-USDT',
    'LINK-USDT', 'PENGU-USDT'
]
RISK_PERCENT      = 1.0
STOP_LOSS_PCT     = 1.5
TAKE_PROFIT_PCT   = 3.0
TRAILING_PCT      = 1.0
LSTM_CONFIDENCE   = 0.75
TIMEFRAME         = '1h'
LOOKBACK          = 200
SIGNAL_COOLDOWN   = 3600
UPDATE_TRAILING_INTERVAL = 300
INITIAL_EPOCHS    = 5
RETRAIN_EPOCHS    = 2
RETRAIN_INTERVAL  = 30 * 60          # 30 минут

lstm_models       = {}
traders           = {}
last_signal_time  = {}
last_trailing_update = {}
last_retrain_time = 0
total_trades      = 0

print("✅ [СТАРТ] Quantum Edge AI Bot запущен на {} криптопарах".format(len(SYMBOLS)))
print(f"📊 ПАРЫ: {', '.join(SYMBOLS)}")
print(f"🧠 LSTM: порог уверенности {LSTM_CONFIDENCE * 100}%")
print(f"💸 Риск: {RISK_PERCENT}% от депозита на сделку")
print(f"⛔ Стоп-лосс: {STOP_LOSS_PCT}% | 🎯 Тейк-профит: {TAKE_PROFIT_PCT}%")
print(f"📈 Трейлинг-стоп: {TRAILING_PCT}% от цены")
print(f"⏳ Кулдаун: {SIGNAL_COOLDOWN} сек. на пару")
print(f"🔄 Дообучение: каждые {RETRAIN_INTERVAL // 60} минут на {RETRAIN_EPOCHS} эпохах")

# --------------------- helpers ---------------------
_bingx_markets = None   # кэш загруженных рынков

def market_exists(symbol: str) -> bool:
    """Проверяет наличие символа на BingX (swap). Кэширует markets при первом вызове."""
    global _bingx_markets
    if _bingx_markets is None:
        try:
            exch = ccxt.bingx({'options': {'defaultType': 'swap'}, 'enableRateLimit': True})
            exch.load_markets()
            _bingx_markets = exch.markets
        except Exception as e:
            print(f'⚠️ market_exists: не удалось загрузить рынки – {e}')
            return False
    return symbol in _bingx_markets

def initialize_models():
    global lstm_models
    os.makedirs('weights', exist_ok=True)
    for s in SYMBOLS:
        lstm_models[s] = LSTMPredictor(lookback=60, model_dir='weights')

def perform_initial_training():
    """Последовательное обучение 5 эпох, если веса ещё не сохранены."""
    for sym in SYMBOLS:
        if not market_exists(sym):
            print(f'⚠️ {sym}: нет на BingX – пропускаем')
            continue
        if lstm_models[sym].load(sym):          # веса уже есть
            print(f'✅ {sym}: загружена сохранённая модель')
            continue
        print(f'\n🎓 {sym}: первичное обучение ({INITIAL_EPOCHS} эпох)...')
        df = get_bars(sym, TIMEFRAME, 500)
        if df is None or len(df) < 300:
            print(f'❌ {sym}: недостаточно данных')
            continue
        df = calculate_strategy_signals(df, 60)
        ok = lstm_models[sym].train_model(df, sym, epochs=INITIAL_EPOCHS, is_initial=True)
        if ok:
            lstm_models[sym].save(sym)

def perform_retraining():
    """Дообучение 2 эпохи каждые 30 минут."""
    global last_retrain_time
    if time.time() - last_retrain_time < RETRAIN_INTERVAL:
        return
    print(f'\n🔄 Начало дообучения ({RETRAIN_EPOCHS} эпох)...')
    for sym in SYMBOLS:
        if not market_exists(sym):
            continue
        print(f'🧠 {sym}: дообучение...')
        df = get_bars(sym, TIMEFRAME, LOOKBACK)
        if df is None or len(df) < 100:
            continue
        df = calculate_strategy_signals(df, 60)
        ok = lstm_models[sym].train_model(df, sym, epochs=RETRAIN_EPOCHS, is_initial=False)
        if ok:
            lstm_models[sym].save(sym)
    last_retrain_time = time.time()

# --------------------- основной цикл ---------------------
def run_strategy():
    global last_signal_time, last_trailing_update, last_retrain_time, total_trades

    initialize_models()
    perform_initial_training()
    last_retrain_time = time.time()

    print('\n🚀 Бот полностью запущен и готов к торговле!')
    while True:
        try:
            perform_retraining()
            for symbol in SYMBOLS:
                if not market_exists(symbol):
                    continue
                print(f"\n--- [{time.strftime('%H:%M:%S')}] {symbol} ---")
                df = get_bars(symbol, TIMEFRAME, LOOKBACK)
                if df is None or len(df) < 100:
                    print(f"❌ Недостаточно данных для {symbol}")
                    continue
                df = calculate_strategy_signals(df, 60)
                current_price = df['close'].iloc[-1]
                buy_signal  = df['buy_signal'].iloc[-1]
                sell_signal = df['sell_signal'].iloc[-1]
                long_score  = df['long_score'].iloc[-1]
                short_score = df['short_score'].iloc[-1]

                if time.time() - last_signal_time.get(symbol, 0) < SIGNAL_COOLDOWN:
                    print(f"⏳ Кулдаун: {symbol} — пропускаем")
                    continue

                lstm_prob = lstm_models[symbol].predict_next(df)
                lstm_conf = lstm_prob > LSTM_CONFIDENCE
                print(f"🧠 LSTM: {lstm_prob:.2%} → {'✅' if lstm_conf else '❌'}")

                strong = (buy_signal and long_score >= 5) or (sell_signal and short_score >= 5)
                if strong and lstm_conf:
                    side = 'buy' if buy_signal else 'sell'
                    print(f"🎯 [СИГНАЛ] {side.upper()} на {symbol}")
                    atr     = df['atr'].iloc[-1]
                    equity  = 100.0
                    risk_am = equity * (RISK_PERCENT / 100)
                    amount  = risk_am / (atr * 1.5) if atr > 0 else 0.001
                    amount  = max(amount, 0.001)
                    print(f"📊 Размер позиции: {amount:.6f}")
                    order   = traders[symbol].place_order(
                        side=side,
                        amount=amount,
                        stop_loss_percent=STOP_LOSS_PCT,
                        take_profit_percent=TAKE_PROFIT_PCT
                    )
                    if order:
                        total_trades += 1
                        last_signal_time[symbol] = time.time()
                else:
                    print(f"⚠️ {symbol}: сигнал слабый или LSTM не уверен")

            # обновление трейлинг-стопов каждые 5 минут
            if time.time() - last_trailing_update.get('global', 0) > UPDATE_TRAILING_INTERVAL:
                for s in SYMBOLS:
                    if market_exists(s):
                        traders[s].update_trailing_stop()
                last_trailing_update['global'] = time.time()

            # тест-ордер полностью удалён – ничего не мешает обучению
            time.sleep(60)
        except Exception as e:
            print(f"❌ КРИТ: {e}")
            time.sleep(60)

# --------------------- flask ---------------------
@app.before_request
def start_bot_once():
    global _bot_started
    if not _bot_started:
        threading.Thread(target=run_strategy, daemon=True).start()
        _bot_started = True

@app.route('/')
def wake_up():
    trained = sum(1 for s in SYMBOLS if os.path.exists(f'weights/lstm_{s.replace("-","_")}.weights.h5'))
    return (f"✅ Quantum Edge AI Bot is LIVE on {len(SYMBOLS)} cryptos!<br>"
            f"📊 Trained models: {trained}/{len(SYMBOLS)}<br>"
            f"🔄 Retraining every {RETRAIN_INTERVAL//60} min"), 200

@app.route('/health')
def health():
    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
