# download_weights.py
import os
import requests
import zipfile
import shutil
import logging

logger = logging.getLogger("bot")
WEIGHTS_DIR = os.path.join(os.path.dirname(__file__), "weights")
ZIP_URL = "https://github.com/soul-code-tech/quantum-edge-ai-bot/archive/refs/heads/weights.zip"


def download_weights():
    os.makedirs(WEIGHTS_DIR, exist_ok=True)
    tmp_zip = "/tmp/weights.zip"
    logger.info("Скачиваем ветку weights с GitHub...")
    r = requests.get(ZIP_URL, stream=True, timeout=30)
    if r.status_code != 200:
        logger.warning(f"GitHub вернул {r.status_code} – пропускаем.")
        return
    with open(tmp_zip, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)
    with zipfile.ZipFile(tmp_zip, "r") as z:
        z.extractall("/tmp")
    src = "/tmp/quantum-edge-ai-bot-weights/weights"
    if os.path.exists(src):
        shutil.rmtree(WEIGHTS_DIR, ignore_errors=True)
        shutil.move(src, WEIGHTS_DIR)
        logger.info("✅ Веса загружены в weights/")
    os.remove(tmp_zip)
