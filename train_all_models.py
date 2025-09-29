# train_all_models.py
import os
os.environ["WEIGHTS_DIR"] = "weights"

from config import SYMBOLS
from trainer import train_one

os.makedirs("weights", exist_ok=True)

print("=" * 60)
print("🤖 GitHub Action: начинаем обучение моделей")
print("📁 Веса будут сохранены в папку weights/")
print("=" * 60)

ok = 0
for s in SYMBOLS:
    print(f"🧠 Action обучает {s} (5 эпох)...")
    if train_one(s, epochs=5):
        ok += 1
        print(f"✅ {s} обучена и сохранена в weights/")
    else:
        print(f"❌ {s} не обучена — пропускаем")
print(f"📊 Итог: {ok}/{len(SYMBOLS)} моделей обучено")
print("✅ GitHub Action завершил обучение")
