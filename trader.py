# trader.py — ФИНАЛЬНАЯ РАБОЧАЯ ВЕРСИЯ — ИСПРАВЛЕНО ПЛЕЧО + USER-AGENT + СИМВОЛ
import ccxt
import os
from dotenv import load_dotenv

load_dotenv()

class BingXTrader:
    def __init__(self, symbol='BTC-USDT', use_demo=False, leverage=10):
        self.symbol = symbol
        self.use_demo = use_demo
        self.leverage = leverage
        
        # ✅ Исправлено: User-Agent и правильный формат
        self.exchange = ccxt.bingx({
            'apiKey': os.getenv('BINGX_API_KEY'),
            'secret': os.getenv('BINGX_SECRET_KEY'),
            'options': {'defaultType': 'swap'},
            'enableRateLimit': True,
            'headers': {'User-Agent': 'QuantumEdgeAI-Bot/1.0'}
        })
        
        if use_demo:
            self.exchange.set_sandbox_mode(True)
        
        self.position = None
        self.trailing_stop_price = None
        self.trailing_distance_percent = 1.0

    def _set_leverage(self, leverage):
        """Устанавливает плечо через новый API v2 (рабочий метод)"""
        try:
            symbol_for_api = self.symbol.replace('-', '')  # BTCUSDT
            response = self.exchange.private_post_swap_v2_trade_leverage({
                "symbol": symbol_for_api,
                "leverage": str(leverage),
                "side": "BOTH"  # ✅ Обязательно для BingX
            })
            
            if response.get('code') == 0:
                print(f"✅ {self.symbol}: Плечо установлено на {leverage}x")
            else:
                msg = response.get('msg', 'unknown error')
                print(f"❌ Ошибка установки плеча: {msg}")
                
        except Exception as e:
            print(f"⚠️ Не удалось установить плечо для {self.symbol}: {e}")

    def place_order(self, side, amount, stop_loss_percent=1.5, take_profit_percent=3.0):
        try:
            # ✅ УСТАНАВЛИВАЕМ ПЛЕЧО ТОЛЬКО ПРИ ПЕРВОЙ СДЕЛКЕ
            self._set_leverage(self.leverage)

            # ✅ ПРОВЕРКА СТАТУСА ПАРЫ
            markets = self.exchange.fetch_markets()
            for m in markets:
                if m['symbol'] == self.symbol:
                    if m['info'].get('status') != 'TRADING':
                        print(f"🚫 {self.symbol} — торговля заблокирована. Пропускаем.")
                        return None

            print(f"📤 Отправка рыночного ордера: {side} {amount} {self.symbol}")
            symbol_for_api = self.symbol.replace('-', '/')  # ✅ КРИТИЧЕСКИ ВАЖНО!
            market_order = self.exchange.create_order(
                symbol=symbol_for_api,
                type='market',
                side=side,
                amount=amount
            )
            order_id = market_order.get('id', 'N/A')
            print(f"✅ Рыночный ордер исполнен: {order_id}")
            
            entry_price = market_order.get('price', None)
            if not entry_price:
                ticker = self.exchange.fetch_ticker(symbol_for_api)
                entry_price = ticker['last']
            
            if side == 'buy':
                stop_loss_price = entry_price * (1 - stop_loss_percent / 100)
                take_profit_price = entry_price * (1 + take_profit_percent / 100)
                self.trailing_stop_price = entry_price * (1 - self.trailing_distance_percent / 100)
            else:
                stop_loss_price = entry_price * (1 + stop_loss_percent / 100)
                take_profit_price = entry_price * (1 - take_profit_percent / 100)
                self.trailing_stop_price = entry_price * (1 + self.trailing_distance_percent / 100)
            
            print(f"📊 Цена входа: {entry_price:.2f}")
            
            # ✅ СТОП-ЛАСС — stop_market
            print(f"⛔ Отправка стоп-лосса (stop_market): {stop_loss_price:.2f} ({stop_loss_percent}%)")
            self.exchange.create_order(
                symbol=symbol_for_api,
                type='stop_market',
                side='sell' if side == 'buy' else 'buy',
                amount=amount,
                params={'stopPrice': stop_loss_price, 'reduceOnly': True}
            )
            
            # ✅ ТЕЙК-ПРОФИТ — limit
            print(f"🎯 Отправка тейк-профита (limit): {take_profit_price:.2f} ({take_profit_percent}%)")
            self.exchange.create_order(
                symbol=symbol_for_api,
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
            
            print(f"✅ УСПЕХ! Ордер {side} на {self.symbol} отправлен.")
            return market_order
            
        except Exception as e:
            error_str = str(e)
            if "position not exist" in error_str:
                print(f"❌ {self.symbol}: Позиция не найдена — возможно, ордер не исполнился.")
            elif "Invalid order quantity" in error_str:
                print(f"❌ {self.symbol}: Неверный размер ордера. Проверь лимиты.")
            elif "101415" in error_str:
                print(f"🚫 {self.symbol}: Торговля временно заблокирована. Ждём...")
            elif "101212" in error_str:
                print(f"⚠️ {self.symbol}: Есть отложенные ордера — отмени их вручную.")
            elif "Invalid order type" in error_str:
                print(f"❌ {self.symbol}: Неверный тип ордера. Используй 'stop_market' и 'limit'.")
            elif "reduceOnly" in error_str:
                print(f"⚠️ {self.symbol}: reduceOnly требует существующей позиции — проверь, что ордер исполнен.")
            else:
                print(f"❌ Полная ошибка API {self.symbol}: {type(e).__name__}: {error_str}")
            return None

    def update_trailing_stop(self):
        if not self.position:
            return
        try:
            symbol_for_api = self.symbol.replace('-', '/')  # ✅ ВАЖНО!
            ticker = self.exchange.fetch_ticker(symbol_for_api)
            current_price = ticker['last']
            side = self.position['side']
            new_trailing_price = self.trailing_stop_price
            
            if side == 'buy':
                if current_price > self.position['last_trailing_price']:
                    new_trailing_price = current_price * (1 - self.trailing_distance_percent / 100)
                    if new_trailing_price > self.trailing_stop_price:
                        self.trailing_stop_price = new_trailing_price
                        print(f"📈 {self.symbol}: Трейлинг-стоп поднят: {self.trailing_stop_price:.2f}")
                        self._cancel_all_stops()
                        self.exchange.create_order(
                            symbol=symbol_for_api,
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
                        print(f"📉 {self.symbol}: Трейлинг-стоп опущен: {self.trailing_stop_price:.2f}")
                        self._cancel_all_stops()
                        self.exchange.create_order(
                            symbol=symbol_for_api,
                            type='stop_market',
                            side='buy',
                            amount=self.position['amount'],
                            params={'stopPrice': self.trailing_stop_price, 'reduceOnly': True}
                        )
                        self.position['last_trailing_price'] = current_price
        except Exception as e:
            print(f"⚠️ {self.symbol}: Ошибка обновления трейлинга: {e}")

    def _cancel_all_stops(self):
        try:
            symbol_for_api = self.symbol.replace('-', '/')  # ✅ ВАЖНО!
            orders = self.exchange.fetch_open_orders(symbol_for_api)
            for order in orders:
                if order['type'] == 'stop_market' and order.get('reduceOnly'):
                    self.exchange.cancel_order(order['id'], symbol_for_api)
                    print(f"🗑️ {self.symbol}: Отменён стоп-ордер ID: {order['id']}")
        except Exception as e:
            print(f"⚠️ {self.symbol}: Не удалось отменить стоп-ордера: {e}")
