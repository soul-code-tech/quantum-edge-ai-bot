import os
import logging
import ccxt
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("trader")

class BingXTrader:
    def __init__(self, symbol='BTC-USDT', use_demo=False, leverage=3):
        self.symbol = symbol
        self.use_demo = use_demo
        self.leverage = leverage
        self.exchange = ccxt.bingx({
            'apiKey': os.getenv('BINGX_API_KEY'),
            'secret': os.getenv('BINGX_SECRET_KEY'),
            'options': {'defaultType': 'swap'},
            'enableRateLimit': True,
        })
        if use_demo:
            self.exchange.set_sandbox_mode(True)
        self._set_leverage(leverage, "LONG")
        self.position = None
        self.trailing_stop_price = None
        self.trailing_distance_percent = 1.0

    def _set_leverage(self, leverage):
        try:
            self.exchange.load_markets()  # ← ленивая
            self.exchange.set_leverage(leverage, symbol=self.symbol)
            print(f"✅ {self.symbol}: плечо установлено на {leverage}x")
        except Exception as e:
            print(f"⚠️ Плечо {self.symbol}: {e}")

    def place_order(self, side, amount, stop_loss_percent=1.5, take_profit_percent=3.0):
        try:
            self.exchange.load_markets()  # ← ленивая
            if self.symbol not in self.exchange.markets:
                print(f"{self.symbol} отсутствует на BingX – пропускаем")
                return None

            logger.info(f"📤 Отправка рыночного ордера: {side} {amount} {self.symbol}")
            market_order = self.exchange.create_order(
                symbol=self.symbol,
                type='market',
                side=side,
                amount=amount
            )
            order_id = market_order.get('id', 'N/A')
            logger.info(f"✅ Рыночный ордер исполнен: {order_id}")

            entry_price = market_order.get('price', None)
            if not entry_price:
                ticker = self.exchange.fetch_ticker(self.symbol)
                entry_price = ticker['last']

            if side == 'buy':
                stop_loss_price = entry_price * (1 - stop_loss_percent / 100)
                take_profit_price = entry_price * (1 + take_profit_percent / 100)
                self.trailing_stop_price = entry_price * (1 - self.trailing_distance_percent / 100)
            else:
                stop_loss_price = entry_price * (1 + stop_loss_percent / 100)
                take_profit_price = entry_price * (1 - take_profit_percent / 100)
                self.trailing_stop_price = entry_price * (1 + self.trailing_distance_percent / 100)

            logger.info(f"📊 Цена входа: {entry_price:.2f}")
            logger.info(f"⛔ Стоп-лосс: {stop_loss_price:.2f} ({stop_loss_percent}%)")
            logger.info(f"🎯 Тейк-профит: {take_profit_price:.2f} ({take_profit_percent}%)")

            self.exchange.create_order(
                symbol=self.symbol,
                type='stop_market',
                side='sell' if side == 'buy' else 'buy',
                amount=amount,
                params={'stopPrice': stop_loss_price, 'reduceOnly': True}
            )
            self.exchange.create_order(
                symbol=self.symbol,
                type='limit',
                side='sell' if side == 'buy' else 'buy',
                amount=amount,
                price=take_profit_price,
                params={'reduceOnly': True}
            )

            self.position = {
                'side': side,
                'entry_price': entry_price,
                'amount': amount,
                'last_trailing_price': entry_price
            }
            logger.info(f"✅ УСПЕХ! Ордер {side} на {self.symbol} отправлен.")
            return market_order

        except Exception as e:
            logger.error(f"❌ Ордер {self.symbol}: {type(e).__name__}: {e}")
            return None

    def update_trailing_stop(self):
        if not self.position:
            return
        try:
            self.exchange.load_markets()
            ticker = self.exchange.fetch_ticker(self.symbol)
            current_price = float(ticker['last'])
            side = self.position['side']
            new_trailing_price = self.trailing_stop_price

            if side == 'buy' and current_price > self.position['last_trailing_price']:
                new_trailing_price = current_price * (1 - self.trailing_distance_percent / 100)
                if new_trailing_price > self.trailing_stop_price:
                    self.trailing_stop_price = new_trailing_price
                    logger.info(f"📈 {self.symbol}: трейлинг-стоп поднят до {self.trailing_stop_price:.2f}")
                    self._cancel_all_stops()
                    self.exchange.create_order(
                        symbol=self.symbol,
                        type='stop_market',
                        side='sell',
                        amount=self.position['amount'],
                        params={'stopPrice': self.trailing_stop_price, 'reduceOnly': True}
                    )
                    self.position['last_trailing_price'] = current_price

            elif side == 'sell' and current_price < self.position['last_trailing_price']:
                new_trailing_price = current_price * (1 + self.trailing_distance_percent / 100)
                if new_trailing_price < self.trailing_stop_price:
                    self.trailing_stop_price = new_trailing_price
                    logger.info(f"📉 {self.symbol}: трейлинг-стоп опущен до {self.trailing_stop_price:.2f}")
                    self._cancel_all_stops()
                    self.exchange.create_order(
                        symbol=self.symbol,
                        type='stop_market',
                        side='buy',
                        amount=self.position['amount'],
                        params={'stopPrice': self.trailing_stop_price, 'reduceOnly': True}
                    )
                    self.position['last_trailing_price'] = current_price
        except Exception as e:
            logger.warning(f"⚠️ {self.symbol}: ошибка трейлинга: {e}")

    def _cancel_all_stops(self):
        try:
            self.exchange.load_markets()
            orders = self.exchange.fetch_open_orders(self.symbol)
            for order in orders:
                if order['type'] == 'stop_market' and order.get('reduceOnly'):
                    self.exchange.cancel_order(order['id'], self.symbol)
                    logger.info(f"🗑️ {self.symbol}: отменён стоп-ордер ID: {order['id']}")
        except Exception as e:
            logger.warning(f"⚠️ {self.symbol}: не удалось отменить стоп-ордера: {e}")
