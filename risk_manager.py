# risk_manager.py
def calculate_position_size(df, risk_pct=1.0, account_balance=1000):
    current_price = df['close'].iloc[-1]
    atr = df['atr'].iloc[-1]
    stop_distance = atr * 1.5
    risk_amount = account_balance * (risk_pct / 100)
    position_size = risk_amount / stop_distance
    return max(position_size, 0.001)

def calculate_stop_loss(df, side='long'):
    current_price = df['close'].iloc[-1]
    atr = df['atr'].iloc[-1]
    return current_price - (atr * 1.5) if side == 'long' else current_price + (atr * 1.5)

def calculate_take_profit(df, side='long'):
    sl = calculate_stop_loss(df, side)
    current_price = df['close'].iloc[-1]
    return current_price + (current_price - sl) if side == 'long' else current_price - (sl - current_price)
