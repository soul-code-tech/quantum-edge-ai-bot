# save_weights_to_github.py
import os
import shutil
import subprocess
import sys
from data_fetcher import get_bars
from strategy import calculate_strategy_signals
from lstm_model import LSTMPredictor

SYMBOLS = [
    'BTC-USDT', 'ETH-USDT', 'SOL-USDT', 'BNB-USDT',
    'XRP-USDT', 'DOGE-USDT', 'TON-USDT', 'AVAX-USDT',
    'SHIB-USDT', 'LINK-USDT', 'PENGU-USDT'
]

WEIGHTS_DIR = "weights"          # папка в корне проекта
REMOTE_URL  = "https://github.com/soul-code-tech/quantum-edge-ai-bot.git"

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
    """Создаёт/обновляет ветку weights и пушит папку weights с токеном."""
    try:
        repo_root = os.path.dirname(os.path.abspath(__file__))
        os.chdir(repo_root)

        token = os.environ.get("GH_TOKEN")
        if not token:
            print("❌ GH_TOKEN не установлен – пропускаю пуш.")
            return

        # URL с токеном
        url = f"https://{token}@{REMOTE_URL.split('https://')[1]}"

        # Git-автор
        subprocess.run(["git", "config", "user.email", "bot@quantum-edge.ai"], check=True)
        subprocess.run(["git", "config", "user.name", "QuantumEdge-Bot"], check=True)

        # Устанавливаем remote (если нужно)
        subprocess.run(["git", "remote", "set-url", "origin", url], check=False)

        subprocess.run(["git", "checkout", "-B", "weights"], check=True)
        subprocess.run(["git", "add", "weights/"], check=True)
        subprocess.run(["git", "commit", "-m", "веса моделей"], check=True)
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
