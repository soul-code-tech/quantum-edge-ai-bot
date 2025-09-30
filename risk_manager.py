# risk_manager.py
import pandas as pd

def calculate_position_size(df, risk_pct=1.0, account_balance=1000):
    """Рассчитывает размер позиции на основе ATR и риска."""
    current_price = df['close'].iloc[-1]
    atr = df['atr'].iloc[-1] if 'atr' in df else current_price * 0.01
    stop_distance = atr * 1.5  # 1.5 ATR
    risk_amount = account_balance * (risk_pct / 100)
    position_size = risk_amount / stop_distance
    return max(position_size, 0.001)

def calculate_stop_loss(df, side='long'):
    """Рассчитывает стоп-лосс на основе ATR."""
    current_price = df['close'].iloc[-1]
    atr = df['atr'].iloc[-1] if 'atr' in df else current_price * 0.01
    if side == 'long':
        return current_price - (atr * 1.5)
    else:
        return current_price + (atr * 1.5)

def calculate_take_profit(df, side='long'):
    """Тейк-профит 2:1 относительно стопа."""
    sl = calculate_stop_loss(df, side)
    current_price = df['close'].iloc[-1]
    if side == 'long':
        return current_price + (current_price - sl)
    else:
        return current_price - (sl - current_price)
