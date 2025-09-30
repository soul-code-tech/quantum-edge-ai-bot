import pandas as pd
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange
from ta.trend import SMAIndicator
import numpy as np

def calculate_strategy_signals(df, symbol=None, current_res_minutes=60):
    """
    Рассчитывает торговые сигналы на основе технических индикаторов
    """
    if current_res_minutes <= 15:
        rsi_len, atr_period = 7, 7
    elif current_res_minutes <= 60:
        rsi_len, atr_period = 14, 14
    elif current_res_minutes <= 240:
        rsi_len, atr_period = 21, 21
    else:
        rsi_len, atr_period = 28, 28

    # Основные индикаторы
    df['rsi'] = RSIIndicator(df['close'], rsi_len).rsi()
    df['sma20'] = SMAIndicator(df['close'], 20).sma_indicator()
    df['sma50'] = SMAIndicator(df['close'], 50).sma_indicator()
    df['atr'] = AverageTrueRange(df['high'], df['low'], df['close'], atr_period).average_true_range()

    # Дополнительные индикаторы для LSTM
    df['sma200'] = SMAIndicator(df['close'], 200).sma_indicator()
    
    # Экспоненциальные скользящие средние
    df['ema12'] = df['close'].ewm(span=12).mean()
    df['ema26'] = df['close'].ewm(span=26).mean()
    
    # MACD
    df['macd'] = df['ema12'] - df['ema26']
    df['macd_signal'] = df['macd'].ewm(span=9).mean()
    
    # Bollinger Bands
    df['bb_middle'] = df['close'].rolling(20).mean()
    bb_std = df['close'].rolling(20).std()
    df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
    df['bb_lower'] = df['bb_middle'] - (bb_std * 2)
    df['bb_position'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])
    
    # Трендовый скоринг
    df['trend_score'] = 0
    df.loc[df['close'] > df['sma20'], 'trend_score'] += 1
    df.loc[df['close'] > df['sma50'], 'trend_score'] += 1
    df.loc[df['sma20'] > df['sma50'], 'trend_score'] += 1
    df.loc[df['close'] > df['sma200'], 'trend_score'] += 1  # Долгосрочный тренд
    df.loc[df['macd'] > df['macd_signal'], 'trend_score'] += 1  # MACD сигнал

    # Анализ объема
    df['vol_avg'] = df['volume'].rolling(20).mean()
    df['vol_ratio'] = df['volume'] / df['vol_avg']
    df['strong_volume'] = (df['volume'] > df['vol_avg']) & (df['volume'] > df['volume'].shift(1))
    
    # Волатильность
    df['price_change'] = df['close'].pct_change()
    df['volatility'] = df['price_change'].rolling(20).std() * np.sqrt(252)  # Годовая волатильность
    
    # Поддержка и сопротивление (простые уровни)
    df['resistance'] = df['high'].rolling(50).max()
    df['support'] = df['low'].rolling(50).min()
    df['price_position'] = (df['close'] - df['support']) / (df['resistance'] - df['support'])
    
    # Скоринг для лонгов и шортов
    df['long_score'] = (
        df['trend_score'] + 
        df['strong_volume'].astype(int) + 
        (df['rsi'] > 55).astype(int) +
        (df['rsi'] < 70).astype(int) +  # RSI не перекуплен
        (df['bb_position'] < 0.8).astype(int)  # Цена не у верхней границы BB
    )
    
    df['short_score'] = (
        (7 - df['trend_score']) +  # Инвертируем трендовый скоринг
        df['strong_volume'].astype(int) + 
        (df['rsi'] < 45).astype(int) +
        (df['rsi'] > 30).astype(int) +  # RSI не перепродан
        (df['bb_position'] > 0.2).astype(int)  # Цена не у нижней границы BB
    )

    # Торговые сигналы
    df['buy_signal'] = (df['long_score'] >= 5) & (df['trend_score'] >= 3)
    df['sell_signal'] = (df['short_score'] >= 5) & ((7 - df['trend_score']) >= 3)
    
    # Дополнительные сигналы для анализа
    df['oversold'] = df['rsi'] < 30
    df['overbought'] = df['rsi'] > 70
    df['golden_cross'] = (df['sma20'] > df['sma50']) & (df['sma20'].shift(1) <= df['sma50'].shift(1))
    df['death_cross'] = (df['sma20'] < df['sma50']) & (df['sma20'].shift(1) >= df['sma50'].shift(1))
    
    # Сигнал на основе пробоя уровней
    df['resistance_break'] = (df['close'] > df['resistance']) & (df['close'].shift(1) <= df['resistance'].shift(1))
    df['support_break'] = (df['close'] < df['support']) & (df['close'].shift(1) >= df['support'].shift(1))

    return df

def get_market_regime(df):
    """
    Определяет текущий режим рынка
    Returns: 'trending_up', 'trending_down', 'ranging', 'volatile'
    """
    recent_trend = df['trend_score'].tail(20).mean()
    recent_volatility = df['volatility'].tail(20).mean()
    
    if recent_trend >= 4 and recent_volatility < 0.5:
        return 'trending_up'
    elif recent_trend <= 2 and recent_volatility < 0.5:
        return 'trending_down'
    elif recent_volatility > 0.8:
        return 'volatile'
    else:
        return 'ranging'

def calculate_position_size(df, risk_percent=1.0, account_balance=1000):
    """
    Рассчитывает оптимальный размер позиции на основе ATR и риска
    """
    current_price = df['close'].iloc[-1]
    atr = df['atr'].iloc[-1]
    
    # Расстояние стоп-лосса в процентах
    stop_distance = (atr * 1.5) / current_price * 100
    
    # Размер позиции на основе процента риска
    risk_amount = account_balance * (risk_percent / 100)
    position_size = risk_amount / (stop_distance / 100 * current_price)
    
    return max(position_size, 0.001)  # Минимальный размер позиции
