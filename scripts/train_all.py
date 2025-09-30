# scripts/train_all.py
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from trainer import train_one, load_model

SYMBOLS = [
    "BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT",
    "XRP/USDT:USDT", "DOGE/USDT:USDT", "AVAX/USDT:USDT", "SHIB/USDT:USDT",
    "LINK/USDT:USDT", "PENGU/USDT:USDT"
]

def main():
    print("🚀 Запуск дообучения моделей (каждые 2 часа)")
    os.makedirs("weights", exist_ok=True)
    
    for symbol in SYMBOLS:
        print(f"\n🔄 Обработка {symbol}...")
        model = load_model(symbol)
        if model is not None:
            print(f"  → Модель найдена — дообучаем на 2 эпохах")
            success = train_one(symbol, epochs=2, existing_model=model)
        else:
            print(f"  → Модель не найдена — обучаем с нуля на 5 эпохах")
            success = train_one(symbol, epochs=5)
        
        if success:
            print(f"  ✅ {symbol} успешно обновлён")
        else:
            print(f"  ❌ {symbol} пропущен (ошибка данных или рынка)")

    print("\n🏁 Цикл дообучения завершён")

if __name__ == "__main__":
    main()
