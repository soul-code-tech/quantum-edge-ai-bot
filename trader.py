# trader.py — ИСПРАВЛЕННАЯ ВЕРСИЯ
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

    def place_order(self, side, amount, stop_loss_price, take_profit_price):
        try:
            print(f"📤 Отправка рыночного ордера: {side} {amount}")
            # Отправляем рыночный ордер
            market_order = self.exchange.create_order(
                symbol=self.symbol,
                type='market',
                side=side,
                amount=amount
            )
            order_id = market_order.get('id', 'N/A')
            print(f"✅ Рыночный ордер исполнен: {order_id}")

            # ⏳ Ждём 2 секунды — чтобы позиция зафиксировалась в системе
            print("⏳ Ждём 2 секунды, чтобы позиция открылась...")
            time.sleep(2)

            # Теперь создаём стоп-лосс и тейк-профит
            print(f"⛔ Отправка стоп-лосса: {stop_loss_price}")
            self.exchange.create_order(
                symbol=self.symbol,
                type='stop',
                side='sell' if side == 'buy' else 'buy',
                amount=amount,
                price=stop_loss_price,
                params={'stopPrice': stop_loss_price}
            )

            print(f"🎯 Отправка тейк-профита: {take_profit_price}")
            self.exchange.create_order(
                symbol=self.symbol,
                type='limit',
                side='sell' if side == 'buy' else 'buy',
                amount=amount,
                price=take_profit_price
            )

            return market_order

        except Exception as e:
            error_str = str(e)
            if "position not exist" in error_str:
                print("❌ ОШИБКА: Позиция ещё не открылась — попробуйте увеличить задержку (time.sleep)")
            else:
                print(f"❌ Полная ошибка API: {type(e).__name__}: {error_str}")
            return None
