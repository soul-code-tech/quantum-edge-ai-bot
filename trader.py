# trader.py
import ccxt
import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("trader")

class BingXTrader:
    def __init__(self, symbol='BTC-USDT', use_demo=False, leverage=10):
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
        self.position = None
        self.trailing_stop_price = None
        self.trailing_distance_percent = 1.0  # 1%

    def _set_leverage(self, leverage: int, side: str = "LONG"):
        try:
            self.exchange.set_leverage(leverage, symbol=self.symbol, params={'side': side})
            logger.info(f"✅ {self.symbol}: leverage set to {leverage}x ({side})")
        except Exception as e:
            logger.warning(f"⚠️ could not set leverage for {self.symbol}: {e}")

    def place_order(self, side, amount, stop_loss_percent=1.5, take_profit_percent=3.0):
        try:
            logger.info(f"📤 sending market order: {side} {amount:.6f} {self.symbol}")
            market_order = self.exchange.create_order(
                symbol=self.symbol,
                type='market',
                side=side,
                amount=amount
            )
            order_id = market_order.get('id', 'N/A')
            logger.info(f"✅ market order filled: {order_id}")

            # Устанавливаем плечо после успешного ордера
            self._set_leverage(self.leverage, side.upper())

            # Получаем цену входа
            entry_price = market_order.get('price')
            if not entry_price:
                ticker = self.exchange.fetch_ticker(self.symbol)
                entry_price = ticker['last']

            # Рассчитываем SL/TP
            if side == 'buy':
                stop_loss_price = entry_price * (1 - stop_loss_percent / 100)
                take_profit_price = entry_price * (1 + take_profit_percent / 100)
                self.trailing_stop_price = entry_price * (1 - self.trailing_distance_percent / 100)
            else:
                stop_loss_price = entry_price * (1 + stop_loss_percent / 100)
                take_profit_price = entry_price * (1 - take_profit_percent / 100)
                self.trailing_stop_price = entry_price * (1 + self.trailing_distance_percent / 100)

            logger.info(f"📊 entry: {entry_price:.2f} | SL: {stop_loss_price:.2f} | TP: {take_profit_price:.2f}")

            # Stop-market (reduceOnly)
            self.exchange.create_order(
                symbol=self.symbol,
                type='stop_market',
                side='sell' if side == 'buy' else 'buy',
                amount=amount,
                params={'stopPrice': stop_loss_price, 'reduceOnly': True}
            )

            # Take-profit limit (reduceOnly)
            self.exchange.create_order(
                symbol=self.symbol,
                type='limit',
                side='sell' if side == 'buy' else 'buy',
                amount=amount,
                price=take_profit_price,
                params={'reduceOnly': True}
            )

            # Сохраняем позицию
            self.position = {
                'side': side,
                'entry_price': entry_price,
                'amount': amount,
                'last_trailing_price': entry_price
            }

            # Логируем ордер
            from order_logger import log_order
            log_order(
                symbol=self.symbol,
                side=side,
                amount=amount,
                limit_price=entry_price,
                stop_price=stop_loss_price,
                tp_price=take_profit_price,
                order_id=order_id
            )

            logger.info(f"✅ Позиция открыта: {side} {self.symbol}")
            return market_order

        except Exception as e:
            error_str = str(e)
            if "position not exist" in error_str:
                logger.error(f"❌ {self.symbol}: позиция не найдена — ордер не исполнился?")
            elif "Invalid order quantity" in error_str:
                logger.error(f"❌ {self.symbol}: неверный объём — проверьте минимальный размер.")
            elif "101415" in error_str:
                logger.warning(f"🚫 {self.symbol}: торговля временно заблокирована.")
            elif "101212" in error_str:
                logger.warning(f"⚠️ {self.symbol}: есть pending ордера — отмените вручную.")
            elif "Invalid order type" in error_str:
                logger.error(f"❌ {self.symbol}: неверный тип ордера.")
            elif "reduceOnly" in error_str:
                logger.warning(f"⚠️ {self.symbol}: reduceOnly без позиции — проверьте исполнение.")
            else:
                logger.error(f"❌ API error {self.symbol}: {type(e).__name__}: {error_str}")
            return None

    def update_trailing_stop(self, new_price=None):
        """Обновить трейлинг-стоп до new_price или автоматически по текущей цене."""
        if not self.position:
            return

        try:
            if new_price is not None:
                # Принудительное обновление до заданной цены
                self.trailing_stop_price = new_price
                self._cancel_all_stops()
                side = 'sell' if self.position['side'] == 'buy' else 'buy'
                self.exchange.create_order(
                    symbol=self.symbol,
                    type='stop_market',
                    side=side,
                    amount=self.position['amount'],
                    params={'stopPrice': new_price, 'reduceOnly': True}
                )
                logger.info(f"🔄 {self.symbol}: трейлинг обновлён вручную до {new_price:.2f}")
                return

            # Автоматическое обновление (вызывается из монитора)
            ticker = self.exchange.fetch_ticker(self.symbol)
            current_price = ticker['last']
            side = self.position['side']
            entry = self.position['entry_price']

            if side == 'buy' and current_price > entry * 1.005:
                new_trailing = current_price * (1 - self.trailing_distance_percent / 100)
                if new_trailing > self.trailing_stop_price:
                    self.trailing_stop_price = new_trailing
                    self._cancel_all_stops()
                    self.exchange.create_order(
                        symbol=self.symbol,
                        type='stop_market',
                        side='sell',
                        amount=self.position['amount'],
                        params={'stopPrice': self.trailing_stop_price, 'reduceOnly': True}
                    )
                    self.position['last_trailing_price'] = current_price
                    logger.info(f"📈 {self.symbol}: trailing raised to {self.trailing_stop_price:.2f}")

            elif side == 'sell' and current_price < entry * 0.995:
                new_trailing = current_price * (1 + self.trailing_distance_percent / 100)
                if new_trailing < self.trailing_stop_price:
                    self.trailing_stop_price = new_trailing
                    self._cancel_all_stops()
                    self.exchange.create_order(
                        symbol=self.symbol,
                        type='stop_market',
                        side='buy',
                        amount=self.position['amount'],
                        params={'stopPrice': self.trailing_stop_price, 'reduceOnly': True}
                    )
                    self.position['last_trailing_price'] = current_price
                    logger.info(f"📉 {self.symbol}: trailing lowered to {self.trailing_stop_price:.2f}")

        except Exception as e:
            logger.error(f"⚠️ {self.symbol}: ошибка обновления трейлинга: {e}")

    def _cancel_all_stops(self):
        try:
            orders = self.exchange.fetch_open_orders(self.symbol)
            for order in orders:
                if order.get('type') == 'stop_market' and order.get('reduceOnly'):
                    self.exchange.cancel_order(order['id'], self.symbol)
                    logger.info(f"🗑️ {self.symbol}: отменён stop-order {order['id']}")
        except Exception as e:
            logger.warning(f"⚠️ {self.symbol}: не удалось отменить стопы: {e}")
