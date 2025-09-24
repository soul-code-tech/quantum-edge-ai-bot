# main.py — Полная рабочая версия (без Telegram, с логами, с тестовыми ордерами)

from flask import Flask
import threading
import time
import os
from data_fetcher import get_bars
from strategy import calculate_strategy_signals
from trader import BingXTrader

app = Flask(__name__)
bot_running = False
_bot_started = False  # Флаг для запуска бота один раз

def trading_bot():
    global bot_running
    if bot_running:
        return
    bot_running = True

    print("✅ [СТАРТ] Quantum Edge AI Bot запущен. Анализируем рынок...")
    print("📊 Логи будут обновляться каждую минуту. Ордера в демо — каждые 5 минут.")

    symbol = 'BTC/USDT'
    trader = BingXTrader(symbol=symbol, use_demo=True)  # Демо-режим (VST)
    last_signal_time = 0
    signal_cooldown = 3600  # 1 час между сигналами
    last_forced_order = 0
    force_order_interval = 300  # Принудительный ордер каждые 5 минут (для теста)

    while True:
        try:
            current_time = time.time()
            print(f"\n--- [{time.strftime('%Y-%m-%d %H:%M:%S')}] ---")
            print("🔄 Получаем рыночные данные с BingX...")

            # Получаем последние 100 свечей
            df = get_bars(symbol, '1h', 100)
            if df is None or len(df) < 50:
                print("❌ Не удалось получить достаточно данных. Повтор через 60 сек.")
                time.sleep(60)
                continue

            # Рассчитываем сигналы стратегии
            df = calculate_strategy_signals(df, 60)
            current_price = df['close'].iloc[-1]
            buy_signal = df['buy_signal'].iloc[-1]
            sell_signal = df['sell_signal'].iloc[-1]
            long_score = df['long_score'].iloc[-1]
            short_score = df['short_score'].iloc[-1]

            print(f"📈 Текущая цена: {current_price:.4f} USDT")
            print(f"📊 Скоры: Long={long_score}/6 | Short={short_score}/6")
            print(f"🚦 Сигналы: Buy={buy_signal} | Sell={sell_signal}")

            # Принудительный ордер каждые 5 минут (для проверки подключения к BingX)
            if current_time - last_forced_order > force_order_interval:
                print("\n🎯 [ТЕСТ] Принудительный рыночный ордер BUY (демо-режим)")
                side = 'buy'
                amount = 0.001  # Очень маленькая позиция для теста
                atr = df['atr'].iloc[-1] if 'atr' in df.columns else 50
                stop_loss = current_price - atr * 1.5
                take_profit = current_price + atr * 3

                print(f"💸 Открываем позицию: {side.upper()} {amount} BTC по ~{current_price:.2f}")
                order = trader.place_order(side, amount, stop_loss, take_profit)
                if order:
                    print(f"✅ УСПЕХ! Ордер исполнен. ID: {order.get('id', 'N/A')}")
                    print(f"⛔ Стоп-лосс установлен на: {stop_loss:.2f}")
                    print(f"🎯 Тейк-профит установлен на: {take_profit:.2f}")
                else:
                    print("❌ ОШИБКА: Не удалось открыть ордер. Проверь ключи API и разрешения.")

                last_forced_order = current_time
                print("⏳ Следующий тестовый ордер через 5 минут...")

            # Обычная логика стратегии (если хочешь включить — раскомментируй)
            # if (buy_signal or sell_signal) and (current_time - last_signal_time > signal_cooldown):
            #     # ... твоя логика ...
            #     last_signal_time = current_time

            print("💤 Ждём 60 секунд до следующего анализа...")
            time.sleep(60)

        except Exception as e:
            print(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {type(e).__name__}: {str(e)}")
            print("⏳ Перезапуск анализа через 60 секунд...")
            time.sleep(60)

# Запускаем бота при первом запросе
@app.before_request
def start_bot_once():
    global _bot_started
    if not _bot_started:
        thread = threading.Thread(target=trading_bot, daemon=True)
        thread.start()
        print("🚀 [СИСТЕМА] Фоновый торговый бот успешно запущен!")
        _bot_started = True

# Эндпоинт для "пробуждения" сервиса (UptimeRobot)
@app.route('/')
def wake_up():
    return "✅ Quantum Edge AI Bot is LIVE and analyzing market!", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Flask сервер запущен на порту {port}")
    app.run(host='0.0.0.0', port=port)
