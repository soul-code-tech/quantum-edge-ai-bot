# main.py
import time
import pandas as pd
from data_fetcher import get_bars
from strategy import calculate_strategy_signals
from ml_filter import get_prophet_trend
from trader import BingXTrader
from telegram_notifier import send_telegram_message  # создадим ниже
import os
from dotenv import load_dotenv

load_dotenv()

def main():
    symbol = 'BTC/USDT'
    trader = BingXTrader(symbol=symbol, use_demo=True)  # True = демо (VST), False = реал
    risk_percent = 1.0  # риск 1% от депозита
    last_signal_time = 0
    signal_cooldown = 3600  # 1 час между сигналами

    while True:
        try:
            print("🔄 Получаем данные...")
            df = get_bars(symbol, '1h', 100)
            df = calculate_strategy_signals(df, 60)

            if df['buy_signal'].iloc[-1] or df['sell_signal'].iloc[-1]:
                current_time = time.time()
                if current_time - last_signal_time < signal_cooldown:
                    print("⏳ Кулдаун — пропускаем сигнал")
                    time.sleep(60)
                    continue

                # Фильтр Prophet
                trend_up, pred_price = get_prophet_trend(df)
                current_price = df['close'].iloc[-1]

                side = None
                if df['buy_signal'].iloc[-1] and trend_up:
                    side = 'buy'
                elif df['sell_signal'].iloc[-1] and not trend_up:
                    side = 'sell'

                if side:
                    # Риск-менеджмент: размер позиции = риск / (ATR * 1.5)
                    atr = df['atr'].iloc[-1]
                    stop_dist = atr * 1.5
                    equity = 10.0  # $10 стартовый депозит
                    risk_amount = equity * (risk_percent / 100)
                    amount = risk_amount / stop_dist

                    stop_loss = current_price - stop_dist if side == 'buy' else current_price + stop_dist
                    take_profit = current_price + atr * 3 if side == 'buy' else current_price - atr * 3

                    print(f"🎯 {side.upper()} сигнал подтверждён Prophet!")
                    print(f"📈 Цена: {current_price:.2f}, Прогноз: {pred_price:.2f}")
                    print(f"📊 Размер позиции: {amount:.3f}, SL: {stop_loss:.2f}, TP: {take_profit:.2f}")

                    # Отправляем в Telegram
                    msg = f"🚀 {side.upper()} {symbol}\nЦена: {current_price:.2f}\nПрогноз: {pred_price:.2f}\nПозиция: {amount:.3f}"
                    send_telegram_message(msg)

                    # Открываем ордер (в демо-режиме)
                    trader.place_order(side, amount, stop_loss, take_profit)

                    last_signal_time = current_time

            time.sleep(60)  # проверяем каждую минуту

        except Exception as e:
            print(f"❌ Ошибка в основном цикле: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
