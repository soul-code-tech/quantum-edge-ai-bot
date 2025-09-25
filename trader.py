# trader.py — Quantum Edge AI Bot: BingXTrader (ФИНАЛЬНАЯ РАБОЧАЯ ВЕРСИЯ)
import ccxt
import os
import time
import hashlib
import hmac
import requests
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

        # Устанавливаем плечо через ручной запрос — ОПЦИОНАЛЬНО (если нужно)
        # self._set_leverage(leverage)  # ← ЗАКОММЕНТИРОВАНО — не нужно, если плечо уже установлено

        # Хранение позиции для трейлинга
        self.position = None
        self.trailing_stop_price = None
        self.trailing_distance_percent = 1.0  # 1% от цены

    def _set_leverage(self, leverage):
        """Устанавливает плечо через прямой POST-запрос к BingX (swap) — для полной автоматизации"""
        try:
            timestamp = int(time.time() * 1000)
            symbol_for_api = self.symbol.replace('-', '')  # BTCUSDT
            api_key = os.getenv('BINGX_API_KEY')
            secret_key = os.getenv('BINGX_SECRET_KEY')

            # ✅ ВСЕ ПАРАМЕТРЫ ДЛЯ ПОДПИСИ — КАК СТРОКИ
            query_string = f"symbol={symbol_for_api}&leverage={str(leverage)}&side=BOTH&timestamp={timestamp}"

            # ✅ ГЕНЕРИРУЕМ ПОДПИСЬ
            signature = hmac.new(
                secret_key.encode(),
                query_string.encode(),
                hashlib.sha256
            ).hexdigest()

            # ✅ ТЕЛО ЗАПРОСА — ТОЧНО ТАКИЕ ЖЕ ПАРАМЕТРЫ, КАК В query_string
            payload = {
                "symbol": symbol_for_api,
                "leverage": str(leverage),   # ← СТРОКА!
                "side": "BOTH",              # ← ОБЯЗАТЕЛЬНО!
                "timestamp": timestamp,
                "signature": signature
            }

            headers = {
                'X-BX-APIKEY': api_key,
                'Content-Type': 'application/json'
            }

            # ✅ ПРАВИЛЬНЫЙ URL — ИЗ ДОКУМЕНТАЦИИ
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

            # Получаем цену входа
            def fetch_ticker_safe():
                return self.exchange.fetch_ticker(self.symbol)
            
            ticker = fetch_with_retry(fetch_ticker_safe)
            entry_price = ticker['last']

            # Рассчитываем TP/SL
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
                amount=amount,
                params={'stopPrice': stop_loss_price, 'reduceOnly': True}
            )

            # Тейк-профит
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
        """Обновляет трейлинг-стоп, если цена двинулась в выгодную сторону"""
        if not self.position:
            return

        def fetch_ticker_safe():
            return self.exchange.fetch_ticker(self.symbol)
        
        current_price = fetch_with_retry(fetch_ticker_safe)['last']
        side = self.position['side']
        new_trailing_price = None

        if side == 'buy':
            new_trailing_price = current_price * (1 - self.trailing_distance_percent / 100)
            if new_trailing_price > self.trailing_stop_price:
                self.trailing_stop_price = new_trailing_price
                print(f"📈 {self.symbol}: Трейлинг-стоп обновлён до {self.trailing_stop_price:.2f} (был {self.position['last_trailing_price']:.2f})")
        else:
            new_trailing_price = current_price * (1 + self.trailing_distance_percent / 100)
            if new_trailing_price < self.trailing_stop_price:
                self.trailing_stop_price = new_trailing_price
                print(f"📉 {self.symbol}: Трейлинг-стоп обновлён до {self.trailing_stop_price:.2f} (был {self.position['last_trailing_price']:.2f})")

        self.position['last_trailing_price'] = current_price


# Добавляем функцию fetch_with_retry в этот же файл — чтобы не импортировать из data_fetcher
def fetch_with_retry(func, max_retries=3, delay=2, backoff=1.5):
    """
    Умный retry для API-запросов BingX — с backoff и альтернативными доменами
    """
    base_urls = [
        'https://open-api.bingx.com',
        'https://open-api.bingx.io'
    ]
    
    for attempt in range(max_retries):
        for base_url in base_urls:
            try:
                exchange = ccxt.bingx({
                    'options': {'defaultType': 'swap', 'baseUrl': base_url},
                    'enableRateLimit': True,
                })
                result = func(exchange)
                return result
            except Exception as e:
                if attempt == max_retries - 1 and base_url == base_urls[-1]:
                    raise Exception(f"❌ Все домены и попытки исчерпаны: {e}")
                wait_time = delay * (backoff ** attempt) + random.uniform(0, 1)
                print(f"⚠️ Ошибка при обращении к {base_url}: {e}. Повтор через {wait_time:.1f} сек. (попытка {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
                break  # Переход к следующему домену
