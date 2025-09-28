# strategy.py
import pandas as pd
from ta.trend import EMAIndicator
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange
from data_fetcher import get_funding_rate   # новое

FR_THRESHOLD = 0.05   # 0,05 % / 8ч

def calculate_strategy_signals(df, symbol: str, current_res_minutes=60):
    rsi_len = 14 if current_res_minutes <= 60 else 21
    df['rsi'] = RSIIndicator(df['close'], rsi_len).rsi()
    df['sma20'] = SMAIndicator(df['close'], 20).sma_indicator()
    df['sma50'] = SMAIndicator(df['close'], 50).sma_indicator()
    df['atr'] = AverageTrueRange(df['high'], df['low'], df['close'], 14).average_true_range()
    df['ema200'] = EMAIndicator(df['close'], 200).ema_indicator()
    df['trend'] = (df['close'] > df['ema200']).astype(int)

    # --------- funding-rate фильтр ---------
    current_funding = get_funding_rate(symbol)
    df['funding_filter_long']  = (current_funding <= FR_THRESHOLD)
    df['funding_filter_short'] = (current_funding >= -FR_THRESHOLD)

    df['vol_avg'] = df['volume'].rolling(20).mean()
    df['strong_volume'] = (df['volume'] > df['vol_avg']) & (df['volume'] > df['volume'].shift(1))

    df['long_score']  = df['trend'] + (df['close'] > df['sma20']) + (df['sma20'] > df['sma50']) + df['strong_volume'] + (df['rsi'] > 55)
    df['short_score'] = (1 - df['trend']) + (df['close'] < df['sma20']) + (df['sma20'] < df['sma50']) + df['strong_volume'] + (df['rsi'] < 45)

    # --------- итоговый сигнал ---------
    df['buy_signal']  = (df['long_score'] >= 4) & (df['trend'] == 1) & df['funding_filter_long']
    df['sell_signal'] = (df['short_score'] >= 4) & (df['trend'] == 0) & df['funding_filter_short']
    return df
