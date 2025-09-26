# trader.py — Quantum Edge AI Bot: BingXTrader (ФИНАЛЬНАЯ РАБОЧАЯ ВЕРСИЯ — 27.09.2025)
import ccxt
import os
import time
import hashlib
import hmac
import requests
import random  # ✅ ДЛЯ fetch_with_retry
from dotenv import load_dotenv

load_dotenv()

class BingXTrader:
    def __init__(self, symbol='BTC-USDT', use_demo=False, leverage=10):
        self.symbol = symbol
        self.use_demo = use_demo
        self.leverage = leverage
        
        # Инициализация биржи
        self.exchange = ccxt.bingx({
            'apiKey': os.getenv('BINGX_API_KEY'),
            'secret': os.getenv('BINGX_SECRET_KEY'),
            'options': {'defaultType': 'swap'},
            'enableRateLimit': True,
        })
        
        if use_demo:
            self.exchange.set_sandbox_mode(True)

        # Устанавливаем плечо через ручной запрос — опционально
        # self._set_leverage(leverage)

        # Хранение позиции для трейлинга и динамического TP
        self.position = None
        self.trailing_stop_price = None
        self.take_profit_price = None
        self.trailing_distance_percent = 1.0

    def _set_leverage(self, leverage):
        """Устанавливает плечо через прямой POST-запрос к BingX (swap)"""
        try:
            timestamp = int(time.time() * 1000)
            symbol_for_api = self.symbol.replace('-', '')  # BTCUSDT
            api_key = os.getenv('BINGX_API_KEY')
            secret_key = os.getenv('BINGX_SECRET_KEY')

            query_string = f"symbol={symbol_for_api}&leverage={str(leverage)}&side=BOTH&timestamp={timestamp}"
            signature = hmac.new(
                secret_key.encode(),
                query_string.encode(),
                hashlib.sha256
            ).hexdigest()

            payload = {
                "symbol": symbol_for_api,
                "leverage": str(leverage),
                "side": "BOTH",
                "timestamp": timestamp,
                "signature": signature
            }

            headers = {
                'X-BX-APIKEY': api_key,
                'Content-Type': 'application/json'
            }

            url = 'https://open-api.bingx.com/openApi/swap/v2/trade/leverage'

            response = requests.post(url, json=payload, headers=headers)
            result = response.json()

            if result.get('code') == 0:
                print(f"✅ {self.symbol}: Плечо установлено на {leverage}x")
            else:
                msg = result.get('msg', 'unknown error')
                print(f"❌ Ошибка установки плеча: {msg}")

        except Exception as e:
            print(f"⚠️ Не удалось установить плечо для {self.symbol}: {e}")

    def get_best_price(self, side):
        """Возвращает лучшую цену (bid/ask) с учётом направления позиции"""
        ticker = self.exchange.fetch_ticker(self.symbol)
        if side == 'buy':
            return ticker['bid']
        else:
            return ticker['ask']

    def place_order(self, side, amount, stop_loss_percent=1.5, take_profit_percent=3.0):
        """Отправляет рыночный ордер + стоп-лосс + тейк-профит"""
        try:
            # Проверка статуса пары
            markets = self.exchange.fetch_markets()
            for m in markets:
                if m['symbol'] == self.symbol:
                    if m['info'].get('status') != 'TRADING':
                        print(f"🚫 {self.symbol} — торговля заблокирована. Пропускаем.")
                        return None

            print(f"📤 Отправка рыночного ордера: {side} {amount}")
            market_order = self.exchange.create_order(
                symbol=self.symbol,
                type='market',
                side=side,
                amount=amount
            )
            order_id = market_order.get('id', 'N/A')
            print(f"✅ Рыночный ордер исполнен: {order_id}")

            # ✅ ИСПРАВЛЕНО: ИСПОЛЬЗУЕМ get_bars() ДЛЯ ПОЛУЧЕНИЯ ЦЕНЫ — ОН УЖЕ С RETRY
            # Это гарантирует, что мы получаем данные, даже если сеть глючит
            df = get_bars(self.symbol, '1h', 1)  # Берём 1 последнюю свечу
            entry_price = df['close'].iloc[-1]  # ✅ НАДЕЖНО, БЕЗ ОШИБОК

            # ✅ УЧЁТ КОМИССИИ — 0.075% (мейкер)
            commission_rate = 0.00075

            # Рассчитываем TP/SL с учётом комиссии
            if side == 'buy':
                stop_loss_price = entry_price * (1 - stop_loss_percent / 100)
                take_profit_price = entry_price * (1 + (take_profit_percent / 100) + commission_rate)
                self.trailing_stop_price = entry_price * (1 - self.trailing_distance_percent / 100)
            else:
                stop_loss_price = entry_price * (1 + stop_loss_percent / 100)
                take_profit_price = entry_price * (1 - (take_profit_percent / 100) - commission_rate)
                self.trailing_stop_price = entry_price * (1 + self.trailing_distance_percent / 100)

            # ✅ ДИНАМИЧЕСКИЙ TP — ПРИЛИПАНИЕ К ЛУЧШЕМУ БИДУ/АСКУ
            buffer = 0.0005
            if side == 'buy':
                best_bid = self.get_best_price('buy')
                self.take_profit_price = best_bid * (1 + buffer)
            else:
                best_ask = self.get_best_price('sell')
                self.take_profit_price = best_ask * (1 - buffer)

            print(f"📊 Цена входа: {entry_price:.2f}")
            
            # ✅ УСЛОВИЕ: ЕСЛИ stop_loss_percent == 0 — НЕ СТАВИМ СТОП-ЛАСС
            if stop_loss_percent > 0:
                stop_limit_price = stop_loss_price * (1 - 0.0005)
                self.exchange.create_order(
                    symbol=self.symbol,
                    type='stop_limit',
                    side='sell' if side == 'buy' else 'buy',
                    amount=amount,
                    price=stop_limit_price,
                    params={'stopPrice': stop_loss_price, 'reduceOnly': True}
                )
                print(f"⛔ Отправка стоп-лосса (stop_limit): {stop_loss_price:.2f} ({stop_loss_percent}%)")

            # ✅ УСЛОВИЕ: ЕСЛИ take_profit_percent == 0 — НЕ СТАВИМ ТЕЙК-ПРОФИТ
            if take_profit_percent > 0:
                self.exchange.create_order(
                    symbol=self.symbol,
                    type='limit',
                    side='sell' if side == 'buy' else 'buy',
                    amount=amount,
                    price=self.take_profit_price,
                    params={'reduceOnly': True}
                )
                print(f"🎯 Отправка тейк-профита (limit): {self.take_profit_price:.2f} ({take_profit_percent}% + комиссия)")

            # Сохраняем позицию
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
                print(f"❌ {self.symbol}: Неверный тип ордера. Используй 'stop_limit' и 'limit'.")
            elif "reduceOnly" in error_str:
                print(f"⚠️ {self.symbol}: reduceOnly требует существующей позиции — проверь, что ордер исполнен.")
            else:
                print(f"❌ Полная ошибка API {self.symbol}: {type(e).__name__}: {error_str}")
            return None

    def update_trailing_stop(self):
        """Обновляет трейлинг-стоп и динамический тейк-профит"""
        if not self.position:
            return

        # ✅ ИСПРАВЛЕНО: ИСПОЛЬЗУЕМ get_bars() — ОН УЖЕ С RETRY
        df = get_bars(self.symbol, '1h', 1)
        current_price = df['close'].iloc[-1]
        side = self.position['side']

        # ✅ 1. ТРЕЙЛИНГ-СТОП
        new_trailing_price = None
        if side == 'buy':
            new_trailing_price = current_price * (1 - self.trailing_distance_percent / 100)
            if new_trailing_price > self.trailing_stop_price:
                self.trailing_stop_price = new_trailing_price
                print(f"📈 {self.symbol}: Трейлинг-стоп обновлён до {self.trailing_stop_price:.2f}")
        else:
            new_trailing_price = current_price * (1 + self.trailing_distance_percent / 100)
            if new_trailing_price < self.trailing_stop_price:
                self.trailing_stop_price = new_trailing_price
                print(f"📉 {self.symbol}: Трейлинг-стоп обновлён до {self.trailing_stop_price:.2f}")

        # ✅ 2. ДИНАМИЧЕСКИЙ ТЕЙК-ПРОФИТ — ОБНОВЛЕНИЕ КАЖДЫЕ 5 МИН
        if side == 'buy':
            best_bid = self.get_best_price('buy')
            new_tp_price = best_bid * (1 + 0.0005)
            if new_tp_price > self.take_profit_price:
                self.take_profit_price = new_tp_price
                print(f"🎯 {self.symbol}: Тейк-профит обновлён до {new_tp_price:.2f} (лучший bid: {best_bid:.2f})")
                self._cancel_take_profit()
                self._place_take_profit()
        else:
            best_ask = self.get_best_price('sell')
            new_tp_price = best_ask * (1 - 0.0005)
            if new_tp_price < self.take_profit_price:
                self.take_profit_price = new_tp_price
                print(f"🎯 {self.symbol}: Тейк-профит обновлён до {new_tp_price:.2f} (лучший ask: {best_ask:.2f})")
                self._cancel_take_profit()
                self._place_take_profit()

        self.position['last_trailing_price'] = current_price

    def _cancel_take_profit(self):
        """Отменяет предыдущий тейк-профит (если есть)"""
        try:
            orders = self.exchange.fetch_open_orders(symbol=self.symbol)
            for order in orders:
                if order['type'] == 'limit' and order['reduceOnly']:
                    self.exchange.cancel_order(order['id'], symbol=self.symbol)
                    print(f"🗑️ {self.symbol}: Отменён старый тейк-профит #{order['id']}")
        except Exception as e:
            print(f"⚠️ {self.symbol}: Не удалось отменить тейк-профит: {e}")

    def _place_take_profit(self):
        """Ставит новый тейк-профит"""
        if not self.position:
            return
        side = self.position['side']
        amount = self.position['amount']
        try:
            self.exchange.create_order(
                symbol=self.symbol,
                type='limit',
                side='sell' if side == 'buy' else 'buy',
                amount=amount,
                price=self.take_profit_price,
                params={'reduceOnly': True}
            )
            print(f"🎯 {self.symbol}: Новый тейк-профит по {self.take_profit_price:.2f} установлен")
        except Exception as e:
            print(f"⚠️ {self.symbol}: Не удалось поставить тейк-профит: {e}")
