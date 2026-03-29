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
TIMEFRAME = _clean(os.getenv("TIMEFRAME", "1m"))

# ── Mode pemilihan pair ───────────────────────────────────────────────
# AUTO : Bot otomatis ambil top N pair by volume dari Gate.io (direkomendasikan)
# MANUAL: Gunakan daftar SYMBOLS di bawah atau dari .env
SYMBOL_MODE = _clean(os.getenv("SYMBOL_MODE", "AUTO"))

# Jumlah pair yang diambil saat mode AUTO
TOP_N_SYMBOLS = int(_clean(os.getenv("TOP_N_SYMBOLS", "20")))

# Interval refresh daftar pair (detik). Default 1 jam.
# Bot akan re-fetch top N pair setiap interval ini.
SYMBOL_REFRESH_INTERVAL = int(_clean(os.getenv("SYMBOL_REFRESH_INTERVAL", "3600")))

# Daftar pair manual (dipakai jika SYMBOL_MODE=MANUAL)
SYMBOLS_ENV = _clean(os.getenv(
    "SYMBOLS",
    "BTC/USDT:USDT,ETH/USDT:USDT,SOL/USDT:USDT,DOGE/USDT:USDT,XRP/USDT:USDT,"
    "BNB/USDT:USDT,ADA/USDT:USDT,AVAX/USDT:USDT,LINK/USDT:USDT,DOT/USDT:USDT,"
    "LTC/USDT:USDT,BCH/USDT:USDT,UNI/USDT:USDT,ATOM/USDT:USDT,ETC/USDT:USDT,"
    "FIL/USDT:USDT,NEAR/USDT:USDT,APT/USDT:USDT,ARB/USDT:USDT,OP/USDT:USDT"
))
SYMBOLS = [s.strip() for s in SYMBOLS_ENV.split(",") if s.strip()]

# ── Risk & Position ───────────────────────────────────────────────────
RISK_PER_TRADE   = float(_clean(os.getenv("RISK_PER_TRADE",   "0.01")))
MAX_POSITIONS    = int(_clean(os.getenv("MAX_OPEN_POSITIONS", "5")))
MAX_NOTIONAL_USD = float(_clean(os.getenv("MAX_NOTIONAL_USD", "100")))

print(f"[Settings] MODE={MODE} | SYMBOL_MODE={SYMBOL_MODE} | TF={TIMEFRAME}")
if SYMBOL_MODE == "AUTO":
    print(f"[Settings] Akan fetch top {TOP_N_SYMBOLS} pair by volume saat startup")
else:
    print(f"[Settings] MANUAL {len(SYMBOLS)} pair | MAX_POS={MAX_POSITIONS}")
