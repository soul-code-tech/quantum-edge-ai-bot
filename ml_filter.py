# ml_filter.py
from prophet import Prophet
import pandas as pd

def get_prophet_trend(df, forecast_hours=3):
    # Готовим данные для Prophet
    prophet_df = df[['timestamp', 'close']].rename(columns={'timestamp': 'ds', 'close': 'y'})
    
    # Создаём и обучаем модель
    model = Prophet(daily_seasonality=True, weekly_seasonality=True)
    model.fit(prophet_df)
    
    # Прогноз
    future = model.make_future_dataframe(periods=forecast_hours, freq='H')
    forecast = model.predict(future)
    
    # Тренд: если последняя прогнозная цена выше текущей — тренд вверх
    current_price = df['close'].iloc[-1]
    predicted_price = forecast['yhat'].iloc[-1]
    trend_up = predicted_price > current_price
    
    return trend_up, predicted_price
