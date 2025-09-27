# trader.py — Quantum Edge AI Bot: BingXTrader
import ccxt
import os
from dotenv import load_dotenv

load_dotenv()

class BingXTrader:
    def __init__(self, symbol='BTC-USDT', use_demo=False, leverage=10):
        self.symbol = symbol
        self.use_demo = use_demo
        self.leverage = leverage
        self.trailing_distance_percent = 1.0

        # Инициализация биржи
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
        self.take_profit_price = None

    def _set_leverage(self, leverage):
        """Устанавливает плечо через новый API v2"""
        try:
            symbol_for_api = self.symbol.replace('-', '')
            response = self.exchange.private_post_swap_v2_trade_leverage({
                "symbol": symbol_for_api,
                "leverage": str(leverage),
                "side": "BOTH"
            })
            if response.get('code') == 0:
                print(f"✅ {self.symbol}: Плечо установлено на {leverage}x")
            else:
                msg = response.get('msg', 'unknown error')
                print(f"❌ Ошибка установки плеча: {msg}")
        except Exception as e:
            print(f"⚠️ Не удалось установить плечо для {self.symbol}: {e}")

    def get_min_order_size(self):
        try:
            markets = self.exchange.fetch_markets()
            for market in markets:
                if market['symbol'] == self.symbol:
                    min_qty = market['limits']['amount']['min']
                    if min_qty is None:
                        return 0.001
                    return min_qty
            return 0.001
        except Exception as e:
            print(f"⚠️ Не удалось получить minQty для {self.symbol}: {e}")
            return 0.001

    def get_best_price(self, side):
        ticker = self.exchange.fetch_ticker(self.symbol)
        return ticker['bid'] if side == 'buy' else ticker['ask']

    def fetch_with_retry(self, func, max_retries=3, delay=2, backoff=1.5):
        base_urls = [
            'https://open-api.bingx.com',
            'https://open-api.bingx.io'
        ]
        for attempt in range(max_retries):
            for base_url in base_urls:
                try:
                    new_exchange = ccxt.bingx({
                        'apiKey': os.getenv('BINGX_API_KEY'),
                        'secret': os.getenv('BINGX_SECRET_KEY'),
                        'options': {'defaultType': 'swap', 'baseUrl': base_url},
                        'enableRateLimit': True,
                        'headers': {'User-Agent': 'QuantumEdgeAI-Bot/1.0'}
                    })
                    result = func(new_exchange)
                    self.exchange = new_exchange
                    return result
                except Exception as e:
                    if attempt == max_retries - 1 and base_url == base_urls[-1]:
                        raise Exception(f"❌ Все домены исчерпаны: {e}")
                    wait_time = delay * (backoff ** attempt) + random.uniform(0, 1)
                    print(f"⚠️ Ошибка подключения: {e}. Повтор через {wait_time:.1f} сек. (попытка {attempt+1}/{max_retries})")
                    time.sleep(wait_time)
                    break

    def place_order(self, side, amount, stop_loss_percent=1.5, take_profit_percent=3.0):
        try:
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

            def fetch_ticker_safe(exchange):
                return exchange.fetch_ticker(self.symbol)

            ticker = self.fetch_with_retry(fetch_ticker_safe)
            entry_price = ticker['last']

            commission_rate = 0.00075
            if side == 'buy':
                stop_loss_price = entry_price * (1 - stop_loss_percent / 100)
                take_profit_price = entry_price * (1 + (take_profit_percent / 100) + commission_rate)
                self.trailing_stop_price = entry_price * (1 - self.trailing_distance_percent / 100)
            else:
                stop_loss_price = entry_price * (1 + stop_loss_percent / 100)
                take_profit_price = entry_price * (1 - (take_profit_percent / 100) - commission_rate)
                self.trailing_stop_price = entry_price * (1 + self.trailing_distance_percent / 100)

            buffer = 0.0005
            if side == 'buy':
                best_bid = self.get_best_price('buy')
                self.take_profit_price = best_bid * (1 + buffer)
            else:
                best_ask = self.get_best_price('sell')
                self.take_profit_price = best_ask * (1 - buffer)

            print(f"📊 Цена входа: {entry_price:.2f}")

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
        if not self.position:
            return
        def fetch_ticker_safe(exchange):
            return exchange.fetch_ticker(self.symbol)
        current_price = self.fetch_with_retry(fetch_ticker_safe)['last']
        side = self.position['side']
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
        self.position['last_trailing_price'] = current_price
