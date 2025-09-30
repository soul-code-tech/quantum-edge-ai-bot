# scripts/train_all.py
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from trainer import train_one, load_model

SYMBOLS = [
    "BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT",
    "XRP/USDT:USDT", "DOGE/USDT:USDT", "AVAX/USDT:USDT", "SHIB/USDT:USDT",
    "LINK/USDT:USDT", "PENGU/USDT:USDT"
]

def main():
    os.makedirs("weights", exist_ok=True)
    for symbol in SYMBOLS:
        print(f"🔄 Обучение {symbol}...")
        model = load_model(symbol, lookback=60)
        if model is not None:
            success = train_one(symbol, epochs=2, existing_model=model)
        else:
            success = train_one(symbol, epochs=5)  # первичное
        if success:
            print(f"✅ {symbol} обновлён")
        else:
            print(f"❌ {symbol} пропущен")

if __name__ == "__main__":
    main()
