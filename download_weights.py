# download_weights.py
import os
import requests
import zipfile
import shutil

WEIGHTS_DIR = "/tmp/lstm_weights"
# ваше реальное имя пользователя и репо
REPO = "https://github.com/soul-code-tech/quantum-edge-ai-bot"
BRANCH = "weights"
ZIP_URL = f"{REPO}/archive/refs/heads/{BRANCH}.zip"

def download_weights():
    """Скачивает веса из ветки weights GitHub в /tmp/lstm_weights."""
    os.makedirs(WEIGHTS_DIR, exist_ok=True)
    zip_path = "/tmp/weights.zip"
    print("⬇️  Скачиваем веса из GitHub...")
    r = requests.get(ZIP_URL, stream=True, timeout=30)
    print(f"   URL: {ZIP_URL}")
    print(f"   Status: {r.status_code}")
    if r.status_code != 200:
        print(f"⚠️  GitHub вернул {r.status_code} – пропускаем загрузку.")
        return
    with open(zip_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)
    # проверяем, что это ZIP
    if not zipfile.is_zipfile(zip_path):
        print("⚠️  Скачанный файл не ZIP – пропускаем.")
        os.remove(zip_path)
        return
    with zipfile.ZipFile(zip_path, 'r') as z:
        z.extractall("/tmp")
    # имя папки после распаковки = quantum-edge-ai-bot-weights
    src = f"/tmp/quantum-edge-ai-bot-{BRANCH}/weights"
    if os.path.exists(src):
        shutil.rmtree(WEIGHTS_DIR, ignore_errors=True)
        shutil.move(src, WEIGHTS_DIR)
        print("✅ Веса загружены из GitHub.")
    else:
        print("⚠️  Папка weights не найдена в ZIP – пропускаем.")
    os.remove(zip_path)
