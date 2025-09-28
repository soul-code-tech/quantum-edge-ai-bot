# main.py  (верхний блок)
import threading
import time
import os
import requests
import logging
import traceback                          # для печати стека
from data_fetcher import get_bars, get_funding_rate
from strategy import calculate_strategy_signals
from trader import BingXTrader
from lstm_model import EnsemblePredictor
from trainer import initial_train_all, sequential_trainer, load_model
from download_weights import download_weights

# --------- консольный логгер ---------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]   # ← пишем в stdout (Render видит)
)

logger = logging.getLogger("bot")

# --------- остальные настройки без изменений ---------
SYMBOLS = [
    'BTC-USDT', 'ETH-USDT', 'BNB-USDT', 'SOL-USDT', 'XRP-USDT',
    'ADA-USDT', 'DOGE-USDT', 'DOT-USDT', 'MATIC-USDT', 'LTC-USDT'
]
RISK_PERCENT = 1.0
STOP_LOSS_PCT = 1.5
TAKE_PROFIT_PCT = 3.0
LSTM_CONFIDENCE = 0.75
TIMEFRAME = '1h'
LOOKBACK = 200
MAX_POSITIONS = 3

lstm_models = {}
traders = {}
last_signal_time = {}
total_trades = 0
equity = 100.0

app = Flask(__name__)

# ================== отладочный старт ==================
def start_all():
    try:
        logger.info("=== СТАРТ start_all() ===")
        logger.info("Скачиваем веса...")
        download_weights()

        logger.info("Загружаем модели...")
        to_train = []
        for s in SYMBOLS:
            logger.debug(f"Загрузка {s}")
            model = load_model(s)
            if model:
                lstm_models[s] = model
                traders[s] = BingXTrader(symbol=s, use_demo=True, leverage=3)
            else:
                lstm_models[s] = EnsemblePredictor()
                traders[s] = BingXTrader(symbol=s, use_demo=True, leverage=3)
                to_train.append(s)
        logger.info(f"К обучению: {len(to_train)} пар")

        if to_train:
            initial_train_all(to_train, epochs=5)
            for s in to_train:
                lstm_models[s] = load_model(s) or EnsemblePredictor()

        logger.info("Запуск фонового переобучения (24 ч)...")
        threading.Thread(target=sequential_trainer, args=(SYMBOLS, 3600 * 24, 2), daemon=True).start()

        logger.info("Запуск торговой стратегии...")
        threading.Thread(target=run_strategy, daemon=True).start()

        threading.Thread(target=keep_alive, daemon=True).start()
        logger.info("=== start_all() завершён ===")

    except Exception as e:
        logger.error("КРИТИЧЕСКАЯ ОШИБКА в start_all():")
        logger.error(traceback.format_exc())
        raise   # чтобы процесс упал и Render перезапустил контейнер


# ================== остальное без изменений ==================
def keep_alive():
    host = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
    if not host:
        return
    url = f"https://{host}/health"
    while True:
        try:
            requests.get(url, timeout=10)
        except Exception as e:
            logger.warning(f"keep-alive error: {e}")
        time.sleep(120)


def run_strategy():
    global total_trades, equity
    while True:
        try:
            current_time = time.time()
            open_pos = sum(1 for s in SYMBOLS if traders[s].position is not None)
            for symbol in SYMBOLS:
                if not getattr(lstm_models[symbol], 'is_trained', False):
                    continue
                if current_time - last_signal_time.get(symbol, 0) < 3600:
                    continue

                df = get_bars(symbol, TIMEFRAME, LOOKBACK)
                if df is None or len(df) < 100:
                    continue
                df = calculate_strategy_signals(df, symbol, 60)

                prob = lstm_models[symbol].predict_next(df)
                if prob < LSTM_CONFIDENCE:
                    continue

                buy_signal = df['buy_signal'].iloc[-1]
                sell_signal = df['sell_signal'].iloc[-1]
                strong = (buy_signal and df['long_score'].iloc[-1] >= 4) or (sell_signal and df['short_score'].iloc[-1] >= 4)
                if not strong:
                    continue

                if open_pos >= MAX_POSITIONS:
                    continue

                side = 'buy' if buy_signal else 'sell'
                atr = df['atr'].iloc[-1]
                amount = traders[symbol].calc_position_size(equity, df['close'].iloc[-1], atr)

                order = traders[symbol].place_limit_order(side=side, amount=amount,
                                                        entry=df['close'].iloc[-1],
                                                        sl_pct=STOP_LOSS_PCT,
                                                        tp_pct=TAKE_PROFIT_PCT)
                if order:
                    total_trades += 1
                    last_signal_time[symbol] = current_time
                    open_pos += 1
                    logger.info(f"📈 СДЕЛКА {side} {symbol} {amount} контр.")

            time.sleep(60)
        except Exception as e:
            logger.error(f"Ошибка в run_strategy: {e}")
            logger.error(traceback.format_exc())
            time.sleep(60)


@app.route('/')
def wake_up():
    trained = sum(1 for m in lstm_models.values() if getattr(m, 'is_trained', False))
    return f"✅ Quantum Edge Bot LIVE! Обучено: {trained}/{len(SYMBOLS)}", 200


@app.route('/health')
def health_check():
    return "OK", 200


if __name__ == "__main__":
    # запускаем start_all в отдельном потоке, чтобы Flask не блокировался
    threading.Thread(target=start_all, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"🌐 Flask server starting on port {port}")
    app.run(host='0.0.0.0', port=port)
