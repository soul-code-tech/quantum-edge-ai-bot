# trader.py — ФИНАЛЬНАЯ, РАБОЧАЯ ВЕРСИЯ
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
            market_order = self.exchange.create_order(
                symbol=self.symbol,
                type='market',
                side=side,
                amount=amount
            )
            order_id = market_order.get('id', 'N/A')
            print(f"✅ Рыночный ордер исполнен: {order_id}")

            print("🔍 Проверяем, открылась ли позиция...")
            max_attempts = 10
            for attempt in range(max_attempts):
                time.sleep(1)
                positions = self.exchange.fetch_positions([self.symbol])
                open_position = None
                for pos in positions:
                    if float(pos['contracts']) > 0:
                        open_position = pos
                        break

                if open_position:
                    print(f"🎯 Позиция открылась! Объём: {open_position['contracts']} BTC")
                    break
                else:
                    print(f"⏳ Позиция ещё не открылась... ({attempt + 1}/{max_attempts})")

            if not open_position:
                print("❌ ОШИБКА: Позиция не открылась за 10 секунд. Возможно, ордер не исполнился.")
                return None

            print(f"⛔ Отправка стоп-лосса (stop_market): {stop_loss_price}")
            self.exchange.create_order(
                symbol=self.symbol,
                type='stop_market',  # ✅ ВАЖНО: именно так!
                side='sell' if side == 'buy' else 'buy',
                amount=amount,
                params={'stopPrice': stop_loss_price}
            )

            print(f"🎯 Отправка тейк-профита (limit): {take_profit_price}")
            self.exchange.create_order(
                symbol=self.symbol,
                type='limit',
                side='sell' if side == 'buy' else 'buy',
                amount=amount,
                price=take_profit_price
            )

            print("✅ УСПЕХ! Все ордера отправлены.")
            return market_order

        except Exception as e:
            error_str = str(e)
            if "position not exist" in error_str:
                print("❌ ОШИБКА: Позиция не найдена — возможно, ордер не исполнился или был отменён.")
            elif "Invalid order type" in error_str:
                print("❌ ОШИБКА: Неверный тип ордера. Убедись, что используешь 'stop_market'.")
            else:
                print(f"❌ Полная ошибка API: {type(e).__name__}: {error_str}")
            return None
