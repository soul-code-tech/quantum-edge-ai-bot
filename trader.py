# trader.py
import ccxt
import os
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("bot")

# ----------- Kelly и риск -----------
KELLY_FRACTION = 0.25            # начнём с консервативной доли Kelly
MAX_POSITIONS = 3                # не держим > 3 монет одновременно
MAKER_FEE = 0.0002               # BingX maker rebate ≈ 0,02 %
SLIP_BUFFER = 0.0005             # 0,05 % «подтираем» цену, чтобы 100 % попасть в мейкер

# ----------- минимальные лоты -----------
MIN_LOTS = {
    'BTC-USDT': 0.001,
    'ETH-USDT': 0.001,
    'BNB-USDT': 0.01,
    'SOL-USDT': 0.01,
    'XRP-USDT': 1,
    'ADA-USDT': 1,
    'DOGE-USDT': 1,
    'DOT-USDT': 0.1,
    'MATIC-USDT': 1,
    'LTC-USDT': 0.01
}


class BingXTrader:
    def __init__(self, symbol='BTC-USDT', use_demo=False, leverage=3):
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
        self.position = None

    # ---------- универсальный размер позиции ----------
    def calc_position_size(self, equity: float, entry: float, atr: float, kelly: float = KELLY_FRACTION) -> float:
        risk_usd = kelly * equity
        stop_usd = atr * 1.5
        contracts = risk_usd / stop_usd
        min_contracts = MIN_LOTS.get(self.symbol, 0.001)
        return max(contracts, min_contracts)

    # ---------- post-only лимитный вход ----------
    def place_limit_order(self, side: str, amount: float, entry: float, sl_pct: float, tp_pct: float):
        try:
            ticker = self.exchange.fetch_ticker(self.symbol)
            last = float(ticker['last'])
            limit_price = last * (1 - SLIP_BUFFER) if side == 'buy' else last * (1 + SLIP_BUFFER)

            order = self.exchange.create_order(
                symbol=self.symbol,
                type='limit',
                side=side,
                amount=amount,
                price=limit_price,
                params={'postOnly': True}
            )
            logger.info(f"POST-ONLY {side} {amount} {self.symbol} @ {limit_price:.4f}")

            order = self.exchange.fetch_order(order['id'], self.symbol)
            if order['status'] != 'closed':
                self.exchange.cancel_order(order['id'], self.symbol)
                logger.info(f"Лимит не исполнен, отмена {self.symbol}")
                return None

            self.exchange.set_leverage(self.leverage, symbol=self.symbol.replace('-', ''))

            # стоп и тейк
            if side == 'buy':
                stop_price = limit_price * (1 - sl_pct / 100)
                tp_price = limit_price * (1 + tp_pct / 100)
            else:
                stop_price = limit_price * (1 + sl_pct / 100)
                tp_price = limit_price * (1 - tp_pct / 100)

            # стоп-лимит (reduce-only)
            self.exchange.create_order(
                symbol=self.symbol,
                type='stop_market',
                side='sell' if side == 'buy' else 'buy',
                amount=amount,
                params={'stopPrice': stop_price, 'reduceOnly': True}
            )
            # тейк-лимит (reduce-only)
            self.exchange.create_order(
                symbol=self.symbol,
                type='limit',
                side='sell' if side == 'buy' else 'buy',
                amount=amount,
                price=tp_price,
                params={'reduceOnly': True}
            )

            logger.info(f"✅ Позиция открыта: {side} {amount} {self.symbol}")
            return {
                'side': side,
                'entry': limit_price,
                'amount': amount,
                'stop': stop_price,
                'tp': tp_price
            }

        except Exception as e:
            logger.error(f"Ошибка входа {self.symbol}: {e}")
            return None
