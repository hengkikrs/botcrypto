import threading
from config import settings

class BotState:
    def __init__(self):
        self._lock            = threading.Lock()
        self.is_running       = False

        # FIX: Leverage diturunkan ke 20x (aman untuk scalping multi-pair)
        # FIX: Margin mode diubah ke isolated (melindungi akun dari likuidasi berantai)
        self.leverage         = 20
        self.margin_mode      = 'isolated'

        self.risk_per_trade   = settings.RISK_PER_TRADE
        self.settings_changed = True

    @property
    def running(self):
        with self._lock:
            return self.is_running

    def start(self):
        with self._lock:
            self.is_running = True

    def stop(self):
        with self._lock:
            self.is_running = False

    def set_leverage(self, value):
        with self._lock:
            self.leverage         = value
            self.settings_changed = True

    def get_snapshot(self):
        with self._lock:
            return {
                "is_running":       self.is_running,
                "leverage":         self.leverage,
                "margin_mode":      self.margin_mode,
                "risk_per_trade":   self.risk_per_trade,
                "settings_changed": self.settings_changed,
            }

    def mark_settings_applied(self):
        with self._lock:
            self.settings_changed = False

bot_state = BotState()
