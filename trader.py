# trader.py — ФИНАЛЬНАЯ ВЕРСИЯ С LSTM + ТРЕЙЛИНГ-СТОП
import ccxt
import os
import time
from dotenv import load_dotenv

load_dotenv()

class BingXTrader:
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
        
        # Храним текущую позицию и её трейлинг-стоп
        self.position = None
        self.trailing_stop_price = None
        self.trailing_distance_percent = 1.0  # 1% от цены

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

            # Получаем цену входа
            entry_price = market_order.get('price', None)
            if not entry_price:
                ticker = self.exchange.fetch_ticker(self.symbol)
                entry_price = ticker['last']

            # Рассчитываем TP/SL в процентах
            if side == 'buy':
                stop_loss_price = entry_price * (1 - stop_loss_percent / 100)
                take_profit_price = entry_price * (1 + take_profit_percent / 100)
                self.trailing_stop_price = entry_price * (1 - self.trailing_distance_percent / 100)
            else:  # sell
                stop_loss_price = entry_price * (1 + stop_loss_percent / 100)
                take_profit_price = entry_price * (1 - take_profit_percent / 100)
                self.trailing_stop_price = entry_price * (1 + self.trailing_distance_percent / 100)

            print(f"📊 Цена входа: {entry_price:.2f}")
            print(f"⛔ Отправка стоп-лосса (stop_market): {stop_loss_price:.2f} ({stop_loss_percent}%)")
            print(f"🎯 Отправка тейк-профита (limit): {take_profit_price:.2f} ({take_profit_percent}%)")

            # Отправляем стоп-лосс и тейк-профит
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

            self.exchange.create_order(
                symbol=self.symbol,
                type='limit',
                side='sell' if side == 'buy' else 'buy',
                amount=amount,
                price=take_profit_price,
                params={'reduceOnly': True}
            )

            # Сохраняем позицию для трейлинга
            self.position = {
                'side': side,
                'entry_price': entry_price,
                'amount': amount,
                'last_trailing_price': entry_price
            }

            print("✅ УСПЕХ! Все ордера отправлены (TP/SL + трейлинг активирован)")
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

    def update_trailing_stop(self):
        """Проверяем, нужно ли двигать трейлинг-стоп"""
        if not self.position:
            return

        try:
            ticker = self.exchange.fetch_ticker(self.symbol)
            current_price = ticker['last']
            side = self.position['side']
            new_trailing_price = self.trailing_stop_price

            if side == 'buy':
                if current_price > self.position['last_trailing_price']:
                    new_trailing_price = current_price * (1 - self.trailing_distance_percent / 100)
                    if new_trailing_price > self.trailing_stop_price:
                        self.trailing_stop_price = new_trailing_price
                        print(f"📈 Трейлинг-стоп поднят: {self.trailing_stop_price:.2f}")
                        # Удаляем старый стоп-лосс и ставим новый
                        self._cancel_all_stops()
                        self.exchange.create_order(
                            symbol=self.symbol,
                            type='stop_market',
                            side='sell',
                            amount=self.position['amount'],
                            params={
                                'stopPrice': self.trailing_stop_price,
                                'reduceOnly': True
                            }
                        )
                        self.position['last_trailing_price'] = current_price

            elif side == 'sell':
                if current_price < self.position['last_trailing_price']:
                    new_trailing_price = current_price * (1 + self.trailing_distance_percent / 100)
                    if new_trailing_price < self.trailing_stop_price:
                        self.trailing_stop_price = new_trailing_price
                        print(f"📉 Трейлинг-стоп опущен: {self.trailing_stop_price:.2f}")
                        self._cancel_all_stops()
                        self.exchange.create_order(
                            symbol=self.symbol,
                            type='stop_market',
                            side='buy',
                            amount=self.position['amount'],
                            params={
                                'stopPrice': self.trailing_stop_price,
                                'reduceOnly': True
                            }
                        )
                        self.position['last_trailing_price'] = current_price

        except Exception as e:
            print(f"⚠️ Ошибка обновления трейлинг-стопа: {e}")

    def _cancel_all_stops(self):
        """Удаляем все стоп-ордера перед обновлением"""
        try:
            orders = self.exchange.fetch_open_orders(self.symbol)
            for order in orders:
                if order['type'] == 'stop_market' and order['reduceOnly']:
                    self.exchange.cancel_order(order['id'], self.symbol)
                    print(f"🗑️ Отменён стоп-ордер ID: {order['id']}")
        except Exception as e:
            print(f"⚠️ Не удалось отменить стоп-ордера: {e}")
