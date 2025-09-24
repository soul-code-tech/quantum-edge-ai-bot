# trader.py
import ccxt
import os
from dotenv import load_dotenv

load_dotenv()

class BingXTrader:
    def __init__(self, symbol='BTC-USDT', use_demo=False):
        self.symbol = symbol
        self.use_demo = use_demo  # True = VST демо, False = реал
        self.exchange = ccxt.bingx({
            'apiKey': os.getenv('BINGX_API_KEY'),
            'secret': os.getenv('BINGX_SECRET_KEY'),
            'options': {'defaultType': 'swap'},
            'enableRateLimit': True,
        })
        if use_demo:
            self.exchange.set_sandbox_mode(True)  # Включаем демо-режим (VST)

    def get_position(self):
        positions = self.exchange.fetch_positions([self.symbol])
        for pos in positions:
            if float(pos['contracts']) != 0:
                return pos
        return None

    def place_order(self, side, amount, stop_loss_price, take_profit_price):
        try:
            # Рыночный ордер
            order = self.exchange.create_order(
                symbol=self.symbol,
                type='market',
                side=side,
                amount=amount
            )
            print(f"✅ Ордер {side} на {amount} исполнен: {order['id']}")

            # Стоп-лосс и тейк-профит
            self.exchange.create_order(
                symbol=self.symbol,
                type='stop',
                side='sell' if side == 'buy' else 'buy',
                amount=amount,
                price=stop_loss_price,
                params={'stopPrice': stop_loss_price}
            )
            self.exchange.create_order(
                symbol=self.symbol,
                type='limit',
                side='sell' if side == 'buy' else 'buy',
                amount=amount,
                price=take_profit_price
            )
            return order
        except Exception as e:
            print(f"❌ Ошибка при открытии позиции: {e}")
            return None
