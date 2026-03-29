import math
from config import settings
from config.state import bot_state
from utils.logger import logger

MARGIN_SAFETY_BUFFER = 0.93

class RiskManager:
    def __init__(self, exchange_client):
        self.ex = exchange_client

    def calculate_position_size(self, symbol, entry_price, stop_loss_price, risk_percentage):
        balance = self.ex.get_balance()
        if balance <= 0:
            return 0

        market_info       = self.ex.get_market_info(symbol)
        min_amount        = market_info['min_amount']
        contract_size_btc = market_info['contract_size']

        if contract_size_btc <= 0:
            contract_size_btc = 0.0001

        sl_distance = abs(entry_price - stop_loss_price)
        if sl_distance == 0:
            return 0

        leverage       = bot_state.leverage
        usable_balance = balance * MARGIN_SAFETY_BUFFER
        risk_amount    = balance * risk_percentage

        size_btc        = risk_amount / sl_distance
        size_by_risk    = size_btc / contract_size_btc
        max_by_leverage = (usable_balance * leverage) / (entry_price * contract_size_btc)

        value_per_contract = entry_price * contract_size_btc
        max_by_notional    = settings.MAX_NOTIONAL_USD / value_per_contract

        size_contracts = math.floor(min(size_by_risk, max_by_leverage, max_by_notional))

        if size_contracts < min_amount:
            margin_for_min = (min_amount * contract_size_btc * entry_price) / leverage
            if margin_for_min <= usable_balance:
                size_contracts = int(min_amount)
            else:
                return 0

        margin_required = (size_contracts * contract_size_btc * entry_price) / leverage
        if margin_required > usable_balance:
            size_contracts = max(0, size_contracts - 1)

        final_notional = size_contracts * contract_size_btc * entry_price
        if final_notional > settings.MAX_NOTIONAL_USD * 1.05:
            size_contracts = math.floor(max_by_notional)

        return size_contracts

    def calculate_sl_tp(self, side, entry_price, atr_value):
        """
        SCALPING 1m: Risk Reward 1 : 1.5
        ────────────────────────────────────────────────────────────────
        SL = 0.8 × ATR  → Ketat, sesuai noise TF 1m yang kecil
        TP = 1.2 × ATR  → Realistis, tidak terlalu greedy di 1m

        Kenapa RR 1:1.5 bukan 1:2?
        Di TF 1m, TP terlalu jauh (2×ATR) sering tidak tercapai sebelum
        reversal. RR 1:1.5 dengan win rate 60%+ menghasilkan expectancy
        positif yang lebih konsisten:
          Expectancy = (0.60 × 1.5) - (0.40 × 1.0) = 0.90 - 0.40 = +0.50
        Artinya setiap trade menghasilkan rata-rata +0.5 unit risiko.

        Perbandingan dengan konfigurasi lama (RR 1:2, WR 35%):
          Expectancy = (0.35 × 2.0) - (0.65 × 1.0) = 0.70 - 0.65 = +0.05
        Hampir break-even dan sangat sensitif terhadap slippage & fee.
        """
        sl_mult = 0.8
        tp_mult = 1.2

        if side == "buy":
            sl = entry_price - (sl_mult * atr_value)
            tp = entry_price + (tp_mult * atr_value)
        else:
            sl = entry_price + (sl_mult * atr_value)
            tp = entry_price - (tp_mult * atr_value)

        return round(sl, 4), round(tp, 4)
