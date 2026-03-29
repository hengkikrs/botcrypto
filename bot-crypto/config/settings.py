import os
from dotenv import load_dotenv

load_dotenv()

def _clean(val: str) -> str:
    """Hapus komentar inline dan whitespace dari nilai .env"""
    return val.split("#")[0].strip() if val else ""

API_KEY    = os.getenv("GATEIO_API_KEY", "")
API_SECRET = os.getenv("GATEIO_API_SECRET", "")
TG_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

MODE      = _clean(os.getenv("MODE", "PAPER"))

# Multi-pair dipisahkan dengan koma. Anda bisa ubah dari .env atau di sini
SYMBOLS_ENV = _clean(os.getenv("SYMBOLS", "BTC/USDT:USDT,ETH/USDT:USDT,SOL/USDT:USDT,DOGE/USDT:USDT,XRP/USDT:USDT"))
SYMBOLS   = [s.strip() for s in SYMBOLS_ENV.split(",")]
TIMEFRAME = _clean(os.getenv("TIMEFRAME", "1m"))

RISK_PER_TRADE   = float(_clean(os.getenv("RISK_PER_TRADE", "0.01")))
MAX_POSITIONS    = int(_clean(os.getenv("MAX_OPEN_POSITIONS", "5"))) # Eksekusi 5 trade sekaligus
MAX_NOTIONAL_USD = float(_clean(os.getenv("MAX_NOTIONAL_USD", "100")))

print(f"[Settings] MODE={MODE} | PAIRS={len(SYMBOLS)} terdaftar | TF={TIMEFRAME}")
print(f"[Settings] MAX_POS={MAX_POSITIONS} POSISI BERSAMAAN")