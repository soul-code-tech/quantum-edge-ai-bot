# trader.py — Quantum Edge AI Bot: BingXTrader (рабочая версия)
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

        # Устанавливаем плечо через ручной запрос
        self._set_leverage(leverage)

        # Хранение позиции для трейлинга
        self.position = None
        self.trailing_stop_price = None
        self.trailing_distance_percent = 1.0  # 1% от цены

    def _set_leverage(self, leverage):
        """Устанавливает плечо через прямой POST-запрос к BingX"""
        try:
            # Подготовка данных
            timestamp = int(time.time() * 1000)
            symbol_for_api = self.symbol.replace('-', '')  # BTCUSDT
            api_key = os.getenv('BINGX_API_KEY')
            secret_key = os.getenv('BINGX_SECRET_KEY')

            params = {
                'symbol': symbol_for_api,
                'leverage': str(leverage),
                'timestamp': timestamp
            }

            # Сортируем параметры по ключу и объединяем в строку
            query_string = '&'.join([f"{k}={v}" for k, v in sorted(params.items())])
            
            # Создаём подпись HMAC SHA256
            signature = hmac.new(
                secret_key.encode(),
                query_string.encode(),
                hashlib.sha256
            ).hexdigest()

            headers = {
                'X-BX-APIKEY': api_key,
                'Content-Type': 'application/json'
            }

            url = 'https://open-api.bingx.com/openApi/swap/v2/trade/setLeverage'

            payload = {**params, 'signature': signature}

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
        """
        Открывает рыночную позицию + стоп-лосс (stop_market) + тейк-профит (limit)
        """
        try:
            # 🔍 Проверка статуса пары
            markets = self.exchange.fetch_markets()
            for m in markets:
                if m['symbol'] == self.symbol:
                    status = m['info'].get('status', 'TRADING')
                    if status != 'TRADING':
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

            # 💵 Получаем цену входа
            entry_price = market_order.get('price', None)
            if not entry_price:
                ticker = self.exchange.fetch_ticker(self.symbol)
                entry_price = ticker['last']

            # 📊 Рассчитываем TP/SL в процентах от цены
            if side == 'buy':
                stop_loss_price = entry_price * (1 - stop_loss_percent / 100)
                take_profit_price = entry 
