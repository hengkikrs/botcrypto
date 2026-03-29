import logging
import requests
import time
from config import settings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("trading_bot.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("QuantBot")

def send_telegram_alert(message, retries=3):
    if not settings.TG_TOKEN or not settings.TG_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{settings.TG_TOKEN}/sendMessage"
    payload = {
        "chat_id": settings.TG_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    
    # Tambahkan sistem Retry dan Timeout 15 detik
    for attempt in range(retries):
        try:
            requests.post(url, json=payload, timeout=15)
            break # Jika sukses, keluar dari loop
        except requests.exceptions.ReadTimeout:
            if attempt == retries - 1:
                logger.error(f"TG Error: Timeout setelah {retries} percobaan.")
            time.sleep(2) # Tunggu 2 detik sebelum mencoba lagi
        except Exception as e:
            if attempt == retries - 1:
                logger.error(f"TG Error: {e}")
            time.sleep(2)