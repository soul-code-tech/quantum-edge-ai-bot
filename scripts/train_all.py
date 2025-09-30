# scripts/train_all.py
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from trainer import train_one, load_model
from datetime import datetime, timezone
import json

SYMBOLS = [
    "BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT",
    "XRP/USDT:USDT", "DOGE/USDT:USDT", "AVAX/USDT:USDT", "SHIB/USDT:USDT",
    "LINK/USDT:USDT", "PENGU/USDT:USDT"
]

def should_retrain(symbol):
    meta_file = f"weights/{symbol.replace('/', '').replace(':', '')}.meta.json"
    if not os.path.exists(meta_file):
        return True
    with open(meta_file) as f:
        meta = json.load(f)
    last = datetime.fromisoformat(meta["last_train"].replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - last).days >= 7

def save_meta(symbol):
    meta_file = f"weights/{symbol.replace('/', '').replace(':', '')}.meta.json"
    with open(meta_file, "w") as f:
        json.dump({"last_train": datetime.now(timezone.utc).isoformat()}, f)

def main():
    os.makedirs("weights", exist_ok=True)
    for symbol in SYMBOLS:
        if should_retrain(symbol):
            print(f"🔄 Переобучение {symbol} (Walk-forward 7 дней)...")
            success = train_one(symbol, epochs=5)
            if success:
                save_meta(symbol)
                print(f"✅ {symbol} обновлён")
        else:
            print(f"⏭️ {symbol} — переобучение не требуется")

if __name__ == "__main__":
    main()
