#!/usr/bin/env python3
"""
Одноразовое последовательное обучение ВСЕХ торговых пар (5 эпох).
Запуск: python train_once.py
После выполнения веса лежат в weights/ и больше никаких действий не требуется.
"""
import os
import time
from data_fetcher import get_bars
from strategy import calculate_strategy_signals
from lstm_model import LSTMPredictor

SYMBOLS = [
    'BTC-USDT', 'ETH-USDT', 'SOL-USDT', 'BNB-USDT',
    'XRP-USDT', 'DOGE-USDT', 'TON-USDT', 'AVAX-USDT',
    'SHIB-USDT', 'LINK-USDT', 'PENGU-USDT'
]
TIMEFRAME = '1h'
BARS_FOR_TRAIN = 500        # свечей для обучения
EPOCHS = 5                  # количество эпох
WEIGHTS_DIR = 'weights'

def main():
    os.makedirs(WEIGHTS_DIR, exist_ok=True)
    print('🚀 Начинаем одноразовое обучение 5 эпох на всех парах...')
    for sym in SYMBOLS:
        print(f'\n🎓 {sym}: обучение ({EPOCHS} эпох)...')
        df = get_bars(sym, TIMEFRAME, BARS_FOR_TRAIN)
        if df is None or len(df) < 300:
            print(f'❌ {sym}: недостаточно данных – пропускаем')
            continue
        df = calculate_strategy_signals(df, 60)
        model = LSTMPredictor(lookback=60, model_dir=WEIGHTS_DIR)
        ok = model.train_model(df, sym, epochs=EPOCHS, is_initial=True)
        if ok:
            model.save(sym)
        else:
            print(f'❌ {sym}: обучение не удалось')
    print('\n✅ Одноразовое обучение завершено. Веса сохранены в папке weights/')

if __name__ == '__main__':
    main()
