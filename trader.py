# trader.py
import ccxt
import os
from dotenv import load_dotenv

load_dotenv()


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
        # self._set_leverage(leverage)   # вызываем после первого ордера
        self.position = None
        self.trailing_stop_price = None
        self.trailing_distance_percent = 1.0

    # ----------  leverage  ----------
    def _set_leverage(self, leverage: int, side: str = "LONG"):
        try:
            symbol_for_api = self.symbol.replace('-', '')
            resp = self.exchange.privatePostLinearSwapApiV1TradingSetLeverage({
                'symbol': symbol_for_api,
                'side': side,
                'leverage': str(leverage)
            })
            if resp.get('code') == 0:
                print(f"✅ {self.symbol}: leverage set to {leverage}x {side}")
            else:
                print(f"❌ leverage error: {resp.get('msg')}")
        except Exception as e:
            print(f"⚠️ could not set leverage for {self.symbol}: {e}")

    # ----------  place order  ----------
    def place_order(self, side, amount, stop_loss_percent=1.5, take_profit_percent=3.0):
        try:
            print(f"📤 sending market order: {side} {amount} {self.symbol}")
            market_order = self.exchange.create_order(
                symbol=self.symbol,
                type='market',
                side=side,
                amount=amount
            )
            order_id = market_order.get('id', 'N/A')
            print(f"✅ market order filled: {order_id}")

            # установить плечо ТОЛЬКО после успешного маркет-ордера
            self._set_leverage(self.leverage, side.upper())

            entry_price = market_order.get('price')
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

            print(f"📊 entry price: {entry_price:.2f}")
            print(f"⛔ placing stop-market: {stop_loss_price:.2f} ({stop_loss_percent}%)")
            print(f"🎯 placing take-profit limit: {take_profit_price:.2f} ({take_profit_percent}%)")

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

            print(f"✅ order {side} on {self.symbol} sent successfully.")
            return market_order

        except Exception as e:
            error_str = str(e)
            if "position not exist" in error_str:
                print(f"❌ {self.symbol}: position not found – order may not have filled.")
            elif "Invalid order quantity" in error_str:
                print(f"❌ {self.symbol}: invalid order size – check limits.")
            elif "101415" in error_str:
                print(f"🚫 {self.symbol}: trading temporarily blocked – waiting...")
            elif "101212" in error_str:
                print(f"⚠️ {self.symbol}: pending orders exist – cancel them manually.")
            elif "Invalid order type" in error_str:
                print(f"❌ {self.symbol}: invalid order type – use 'stop_market' & 'limit'.")
            elif "reduceOnly" in error_str:
                print(f"⚠️ {self.symbol}: reduceOnly requires open position – check fill.")
            else:
                print(f"❌ API error {self.symbol}: {type(e).__name__}: {error_str}")
            return None

    # ----------  trailing stop  ----------
    def update_trailing_stop(self):
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
                        print(f"📈 {self.symbol}: trailing raised to {self.trailing_stop_price:.2f}")
                        self._cancel_all_stops()
                        self.exchange.create_order(
                            symbol=self.symbol,
                            type='stop_market',
                            side='sell',
                            amount=self.position['amount'],
                            params={'stopPrice': self.trailing_stop_price, 'reduceOnly': True}
                        )
                        self.position['last_trailing_price'] = current_price

            elif side == 'sell':
                if current_price < self.position['last_trailing_price']:
                    new_trailing_price = current_price * (1 + self.trailing_distance_percent / 100)
                    if new_trailing_price < self.trailing_stop_price:
                        self.trailing_stop_price = new_trailing_price
                        print(f"📉 {self.symbol}: trailing lowered to {self.trailing_stop_price:.2f}")
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
            print(f"⚠️ {self.symbol}: trailing update error: {e}")

    # ----------  helpers  ----------
    def _cancel_all_stops(self):
        try:
            orders = self.exchange.fetch_open_orders(self.symbol)
            for order in orders:
                if order['type'] == 'stop_market' and order.get('reduceOnly'):
                    self.exchange.cancel_order(order['id'], self.symbol)
                    print(f"🗑️ {self.symbol}: cancelled stop-order {order['id']}")
        except Exception as e:
            print(f"⚠️ {self.symbol}: failed to cancel stops: {e}")
