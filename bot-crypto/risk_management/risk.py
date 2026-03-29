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
        if balance <= 0: return 0

        market_info       = self.ex.get_market_info(symbol)
        min_amount        = market_info['min_amount']
        contract_size_btc = market_info['contract_size']

        if contract_size_btc <= 0: contract_size_btc = 0.0001
        sl_distance    = abs(entry_price - stop_loss_price)
        if sl_distance == 0: return 0

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
            else: return 0

        margin_required = (size_contracts * contract_size_btc * entry_price) / leverage
        if margin_required > usable_balance:
            size_contracts = max(0, size_contracts - 1)

        final_notional = size_contracts * contract_size_btc * entry_price
        if final_notional > settings.MAX_NOTIONAL_USD * 1.05: 
            size_contracts = math.floor(max_by_notional)

        return size_contracts

    def calculate_sl_tp(self, side, entry_price, atr_value):
        """
        SWING TRADING: Risk Reward 1 : 2
        SL = 1.5 * ATR (Memberi ruang nafas untuk volatilitas TF 15m)
        TP = 3.0 * ATR (Target cuan 2x lipat dari risiko kerugian)
        """
        if side == "buy":
            sl = entry_price - (1.5 * atr_value)
            tp = entry_price + (3.0 * atr_value)
        else:
            sl = entry_price + (1.5 * atr_value)
            tp = entry_price - (3.0 * atr_value)
            
        return round(sl, 4), round(tp, 4)