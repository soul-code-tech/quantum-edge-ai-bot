# trader.py — ФИНАЛЬНАЯ, ПРОВЕРЕННАЯ, РАБОЧАЯ ВЕРСИЯ (с правильным именем класса)
import ccxt
import os
import time
from dotenv import load_dotenv

load_dotenv()

class BingXTrader:  # ← ЭТО ДОЛЖНО БЫТЬ ТОЧНО ТАК! НЕ ИЗМЕНЯЙ ИМЯ!
    def __init__(self, symbol='BTC-USDT', use_demo=False):
        self.symbol = symbol
        self.use_demo = use_demo
        self.exchange = ccxt.bingx({
            'apiKey': os.getenv('BINGX_API_KEY'),
            'secret': os.getenv('BINGX_SECRET_KEY'),
            'options': {'defaultType': 'swap'},
            'enableRateLimit': True,
        })
        if use_demo:
            self.exchange.set_sandbox_mode(True)

    def place_order(self, side, amount, stop_loss_percent=1.5, take_profit_percent=3.0):
        try:
            print(f"📤 Отправка рыночного ордера: {side} {amount}")
            market_order = self.exchange.create_order(
                symbol=self.symbol,
                type='market',
                side=side,
                amount=amount
            )
            order_id = market_order.get('id', 'N/A')
            print(f"✅ Рыночный ордер исполнен: {order_id}")

            # Получаем цену входа из ордера
            entry_price = market_order.get('price', None)
            if not entry_price:
                ticker = self.exchange.fetch_ticker(self.symbol)
                entry_price = ticker['last']

            # Рассчитываем цены TP/SL в процентах
            if side == 'buy':
                stop_loss_price = entry_price * (1 - stop_loss_percent / 100)
                take_profit_price = entry_price * (1 + take_profit_percent / 100)
            else:  # sell
                stop_loss_price = entry_price * (1 + stop_loss_percent / 100)
                take_profit_price = entry_price * (1 - take_profit_percent / 100)

            print(f"📊 Цена входа: {entry_price:.2f}")
            print(f"⛔ Отправка стоп-лосса (stop_market): {stop_loss_price:.2f} ({stop_loss_percent}%)")
            print(f"🎯 Отправка тейк-профита (limit): {take_profit_price:.2f} ({take_profit_percent}%)")

            # Отправляем стоп-лосс
            self.exchange.create_order(
                symbol=self.symbol,
                type='stop_market',
                side='sell' if side == 'buy' else 'buy',
                amount=amount,
                params={
                    'stopPrice': stop_loss_price,
                    'reduceOnly': True
                }
            )

            # Отправляем тейк-профит
            self.exchange.create_order(
                symbol=self.symbol,
                type='limit',
                side='sell' if side == 'buy' else 'buy',
                amount=amount,
                price=take_profit_price,
                params={'reduceOnly': True}
            )

            print("✅ УСПЕХ! Все ордера отправлены (TP/SL привязаны к цене входа)")
            return market_order

        except Exception as e:
            error_str = str(e)
            if "position not exist" in error_str:
                print("❌ ОШИБКА: Позиция не найдена — возможно, ордер не исполнился.")
            elif "Invalid order quantity" in error_str:
                print("❌ ОШИБКА: Неверный размер ордера. Убедись, что amount > 0.")
            elif "Invalid order type" in error_str:
                print("❌ ОШИБКА: Неверный тип ордера. Используй 'stop_market' и 'limit'.")
            elif "reduceOnly" in error_str:
                print("❌ ОШИБКА: reduceOnly требует существующей позиции — проверь, что ордер исполнен.")
            else:
                print(f"❌ Полная ошибка API: {type(e).__name__}: {error_str}")
            return None
