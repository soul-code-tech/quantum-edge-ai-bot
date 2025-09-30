import ccxt
import os
from dotenv import load_dotenv
import time

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
        
        # Правильная настройка плеча через API v3
        self._set_leverage_v3(leverage)
        
        self.position = None
        self.trailing_stop_price = None
        self.trailing_distance_percent = 1.0
        self.last_leverage_check = 0

    def _set_leverage_v3(self, leverage):
        """Правильная настройка плеча через API v3"""
        try:
            # Используем правильный endpoint для установки плеча
            symbol_for_api = self.symbol.replace('-', '')
            
            # Для BingX используем v3 API endpoint
            response = self.exchange.privatePostLinearSwapApiV3TradingSetLeverage({
                'symbol': symbol_for_api,
                'leverage': str(leverage),
                'side': 'BOTH'  # BOTH для двустороннего плеча
            })
            
            if response.get('code') == 0 or response.get('msg') == 'success':
                print(f"✅ {self.symbol}: Плечо установлено на {leverage}x")
                self.last_leverage_check = time.time()
                return True
            else:
                msg = response.get('msg', 'unknown')
                print(f"❌ Ошибка установки плеча: {msg}")
                
                # Пробуем альтернативный метод через position margin
                try:
                    self.exchange.set_leverage(leverage, self.symbol)
                    print(f"✅ {self.symbol}: Плечо установлено через set_leverage на {leverage}x")
                    return True
                except Exception as e2:
                    print(f"❌ Альтернативный метод также не работает: {e2}")
                    return False
                    
        except Exception as e:
            print(f"⚠️ Не удалось установить плечо для {self.symbol}: {e}")
            
            # Пробуем еще один альтернативный метод
            try:
                self.exchange.set_leverage(leverage, self.symbol)
                print(f"✅ {self.symbol}: Плечо установлено через стандартный метод на {leverage}x")
                return True
            except Exception as e2:
                print(f"❌ Все методы установки плеча не работают: {e2}")
                return False

    def _verify_leverage(self):
        """Проверяет и при необходимости обновляет плечо"""
        current_time = time.time()
        if current_time - self.last_leverage_check > 3600:  # Проверяем каждый час
            try:
                symbol_for_api = self.symbol.replace('-', '')
                response = self.exchange.privateGetLinearSwapApiV3TradingGetLeverage({
                    'symbol': symbol_for_api
                })
                
                if response.get('code') == 0:
                    current_leverage = response.get('data', {}).get('leverage', 1)
                    if float(current_leverage) != self.leverage:
                        print(f"⚠️ {self.symbol}: Текущее плечо {current_leverage}x, требуется {self.leverage}x")
                        self._set_leverage_v3(self.leverage)
                    else:
                        print(f"✅ {self.symbol}: Плечо подтверждено {current_leverage}x")
                
                self.last_leverage_check = current_time
                
            except Exception as e:
                print(f"⚠️ Не удалось проверить плечо для {self.symbol}: {e}")

    def place_order(self, side, amount, stop_loss_percent=1.5, take_profit_percent=3.0):
        """Размещает ордер с учетом правильной работы плеча"""
        try:
            # Проверяем плечо перед размещением ордера
            self._verify_leverage()
            
            print(f"📤 Отправка рыночного ордера: {side} {amount} {self.symbol}")
            
            # Корректируем размер позиции с учетом плеча
            leveraged_amount = amount / self.leverage
            
            market_order = self.exchange.create_order(
                symbol=self.symbol,
                type='market',
                side=side,
                amount=leveraged_amount
            )
            
            order_id = market_order.get('id', 'N/A')
            print(f"✅ Рыночный ордер исполнен: {order_id}")

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

            print(f"📊 Цена входа: {entry_price:.2f}")
            print(f"⛔ Отправка стоп-лосса (stop_market): {stop_loss_price:.2f} ({stop_loss_percent}%)")
            print(f"🎯 Отправка тейк-профита (limit): {take_profit_price:.2f} ({take_profit_percent}%)")

            # Стоп-лосс
            self.exchange.create_order(
                symbol=self.symbol,
                type='stop_market',
                side='sell' if side == 'buy' else 'buy',
                amount=leveraged_amount,
                params={'stopPrice': stop_loss_price, 'reduceOnly': True}
            )

            # Тейк-профит
            self.exchange.create_order(
                symbol=self.symbol,
                type='limit',
                side='sell' if side == 'buy' else 'buy',
                amount=leveraged_amount,
                price=take_profit_price,
                params={'reduceOnly': True}
            )

            self.position = {
                'side': side,
                'entry_price': entry_price,
                'amount': leveraged_amount,
                'last_trailing_price': entry_price,
                'original_amount': amount  # Сохраняем оригинальный размер для расчетов
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
            elif "leverage" in error_str.lower():
                print(f"⚠️ {self.symbol}: Проблема с плечом — пробуем переустановить")
                self._set_leverage_v3(self.leverage)
            else:
                print(f"❌ Полная ошибка API {self.symbol}: {type(e).__name__}: {error_str}")
            return None

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
                        print(f"📈 {self.symbol}: Трейлинг-стоп поднят: {self.trailing_stop_price:.2f}")
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
                        print(f"📉 {self.symbol}: Трейлинг-стоп опущен: {self.trailing_stop_price:.2f}")
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
            print(f"⚠️ {self.symbol}: Ошибка обновления трейлинга: {e}")

    def _cancel_all_stops(self):
        try:
            orders = self.exchange.fetch_open_orders(self.symbol)
            for order in orders:
                if order['type'] == 'stop_market' and order.get('reduceOnly'):
                    self.exchange.cancel_order(order['id'], self.symbol)
                    print(f"🗑️ {self.symbol}: Отменён стоп-ордер ID: {order['id']}")
        except Exception as e:
            print(f"⚠️ {self.symbol}: Не удалось отменить стоп-ордера: {e}")
    
    def get_position_info(self):
        """Получает информацию о текущей позиции"""
        try:
            positions = self.exchange.fetch_positions([self.symbol])
            for position in positions:
                if position['symbol'] == self.symbol and position['contracts'] > 0:
                    return {
                        'side': position['side'],
                        'size': position['contracts'],
                        'entry_price': position['entryPrice'],
                        'unrealized_pnl': position['unrealizedPnl'],
                        'leverage': position['leverage']
                    }
            return None
        except Exception as e:
            print(f"⚠️ Не удалось получить информацию о позиции {self.symbol}: {e}")
            return None
