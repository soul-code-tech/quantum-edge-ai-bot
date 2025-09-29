# train_all_models.py
import os
from config import SYMBOLS
from trainer import train_one

MODEL_DIR = "weights"
os.makedirs(MODEL_DIR, exist_ok=True)

print(f"🤖 Начинаем обучение для {len(SYMBOLS)} пар: {SYMBOLS}")
ok = 0
for s in SYMBOLS:
    print(f"🧠 Обучаем {s}...")
    if train_one(s, epochs=5):
        ok += 1
        print(f"✅ {s} обучена")
    else:
        print(f"❌ {s} не обучена")
print(f"✅ Обучено: {ok}/{len(SYMBOLS)} моделей")
