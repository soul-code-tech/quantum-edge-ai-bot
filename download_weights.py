# download_weights.py
import os
import requests
import zipfile
import shutil

WEIGHTS_DIR = "/tmp/lstm_weights"
REPO = "https://github.com/soul-code-tech/quantum-edge-ai-bot/edit/main/download_weights.py"   # ← замените на своё
BRANCH = "weights"
ZIP_URL = f"{REPO}/archive/refs/heads/{BRANCH}.zip"

def download_weights():
    """Скачивает веса из ветки weights GitHub в /tmp/lstm_weights."""
    os.makedirs(WEIGHTS_DIR, exist_ok=True)
    zip_path = "/tmp/weights.zip"
    print("⬇️  Скачиваем веса из GitHub...")
    r = requests.get(ZIP_URL, stream=True, timeout=30)
    r.raise_for_status()
    with open(zip_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)
    with zipfile.ZipFile(zip_path, 'r') as z:
        z.extractall("/tmp")
    # имя папки после распаковки = YOUR_REPO-weights
    src = f"/tmp/YOUR_REPO-{BRANCH}/weights"
    if os.path.exists(src):
        shutil.rmtree(WEIGHTS_DIR, ignore_errors=True)
        shutil.move(src, WEIGHTS_DIR)
    os.remove(zip_path)
    print("✅ Веса загружены из GitHub.")
