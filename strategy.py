# strategy.py
import pandas as pd
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange
from ta.trend import SMAIndicator
import numpy as np

def calculate_strategy_signals(df, minutes=60):
    df = df.copy()
    rsi_len = 14 if minutes <= 60 else 21
    atr_period = 14 if minutes <= 60 else 21

    df['rsi'] = RSIIndicator(df['close'], rsi_len).rsi()
    df['sma20'] = SMAIndicator(df['close'], 20).sma_indicator()
    df['sma50'] = SMAIndicator(df['close'], 50).sma_indicator()
    df['sma200'] = SMAIndicator(df['close'], 200).sma_indicator()
    df['atr'] = AverageTrueRange(df['high'], df['low'], df['close'], window=atr_period).average_true_range()
    df['vol_avg'] = df['volume'].rolling(20).mean()
    df['strong_volume'] = (df['volume'] > df['vol_avg']) & (df['volume'] > df['volume'].shift(1))
    
    df['trend_score'] = (
        (df['close'] > df['sma20']).astype(int) +
        (df['close'] > df['sma50']).astype(int) +
        (df['sma20'] > df['sma50']).astype(int) +
        (df['close'] > df['sma200']).astype(int)
    )
    
    df['long_score'] = (
        df['trend_score'] +
        df['strong_volume'].astype(int) +
        (df['rsi'] > 55).astype(int) +
        (df['rsi'] < 70).astype(int)
    ).clip(0, 5)
    
    df['volatility'] = df['close'].pct_change().rolling(20).std()
    
    return df

def get_market_regime(df):
    return df['regime'].iloc[-1] if 'regime' in df.columns else 'ranging'
