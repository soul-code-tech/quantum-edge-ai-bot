# save_weights_to_github.py
import os
import shutil
import subprocess
import sys
from data_fetcher import get_bars
from strategy import calculate_strategy_signals
from lstm_model import LSTMPredictor
from trainer import model_path

SYMBOLS = [
    'BTC-USDT', 'ETH-USDT', 'SOL-USDT', 'BNB-USDT',
    'XRP-USDT', 'DOGE-USDT', 'TON-USDT', 'AVAX-USDT',
    'SHIB-USDT', 'LINK-USDT', 'PENGU-USDT'
]

WEIGHTS_DIR = "weights"          # папка в корне проекта

def train_and_save(symbol: str, lookback: int = 60, epochs: int = 5) -> bool:
    """Обучает одну пару и сохраняет веса в WEIGHTS_DIR."""
    try:
        print(f"\n🧠 Обучаем {symbol} (epochs={epochs})...")
        df = get_bars(symbol, "1h", 300)
        if df is None or len(df) < 200:
            print(f"⚠️  Недостаточно данных для {symbol}")
            return False
        df = calculate_strategy_signals(df, 60)

        model = LSTMPredictor(lookback=lookback)
        model.train(df, epochs=epochs)

        # сохраняем веса
        os.makedirs(WEIGHTS_DIR, exist_ok=True)
        dst = os.path.join(WEIGHTS_DIR, symbol.replace("-", "") + ".pkl")
        with open(dst, "wb") as fh:
            import pickle
            pickle.dump({"scaler": model.scaler, "model": model.model}, fh)
        print(f"✅ Веса сохранены в {dst}")
        return True
    except Exception as e:
        print(f"❌ Ошибка при обучении {symbol}: {e}")
        return False

def push_to_github():
    """Создаёт ветку weights и пушит папку weights/."""
    try:
        # переходим в корень проекта (где лежит .git)
        repo_root = os.path.dirname(os.path.abspath(__file__))
        os.chdir(repo_root)

        # создаём ветку weights (если её нет)
        subprocess.run(["git", "checkout", "-B", "weights"], check=True)
        # добавляем папку
        subprocess.run(["git", "add", "weights/"], check=True)
        # коммит
        subprocess.run(["git", "commit", "-m", "веса моделей из /tmp"], check=True)
        # пуш
        subprocess.run(["git", "push", "origin", "weights"], check=True)
        print("✅ Папка weights отправлена в ветку origin/weights")
    except subprocess.CalledProcessError as e:
        print(f"❌ Ошибка Git: {e}")
        sys.exit(1)

def main():
    print("=== Сохранение весов в GitHub ===")
    ok = 0
    for s in SYMBOLS:
        if train_and_save(s, epochs=5):
            ok += 1
    print(f"\n✅ Обучено и сохранено: {ok}/{len(SYMBOLS)} пар")
    push_to_github()
    print("\n🎉 Веса находятся в ветке `weights` на GitHub!")

if __name__ == "__main__":
    main()
