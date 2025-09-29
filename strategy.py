# strategy.py
import pandas as pd
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange
from ta.trend import SMAIndicator

def calculate_strategy_signals(df, symbol: str, current_res_minutes=60):
    if current_res_minutes <= 15:
        rsi_len, atr_period = 7, 7
    elif current_res_minutes <= 60:
        rsi_len, atr_period = 14, 14
    elif current_res_minutes <= 240:
        rsi_len, atr_period = 21, 21
    else:
        rsi_len, atr_period = 28, 28

    df['rsi'] = RSIIndicator(df['close'], rsi_len).rsi()
    df['sma20'] = SMAIndicator(df['close'], 20).sma_indicator()
    df['sma50'] = SMAIndicator(df['close'], 50).sma_indicator()
    df['atr'] = AverageTrueRange(df['high'], df['low'], df['close'], atr_period).average_true_range()

    df['trend_score'] = 0
    df.loc[df['close'] > df['sma20'], 'trend_score'] += 1
    df.loc[df['close'] > df['sma50'], 'trend_score'] += 1
    df.loc[df['sma20'] > df['sma50'], 'trend_score'] += 1

    df['vol_avg'] = df['volume'].rolling(20).mean()
    df['strong_volume'] = (df['volume'] > df['vol_avg']) & (df['volume'] > df['volume'].shift(1))

    df['long_score'] = df['trend_score'] + df['strong_volume'].astype(int) + (df['rsi'] > 55).astype(int)
    df['short_score'] = (3 - df['trend_score']) + df['strong_volume'].astype(int) + (df['rsi'] < 45).astype(int)

    df['buy_signal'] = df['long_score'] >= 4
    df['sell_signal'] = df['short_score'] >= 4

    return df
