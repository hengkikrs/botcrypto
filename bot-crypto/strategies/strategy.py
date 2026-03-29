import numpy as np
from utils.logger import logger

class TrendFollowingStrategy:
    def generate_signal(self, df, orderbook=None):
        if df.empty or len(df) < 3:
            return None, None, None, "Data tidak cukup"

        current = df.iloc[-1]
        prev    = df.iloc[-2]

        close   = float(current['close'])
        low     = float(current['low'])
        high    = float(current['high'])
        
        ema200  = float(current['EMA200'])
        ema9    = float(current['EMA9'])
        ema21   = float(current['EMA21'])
        
        bb_low  = float(current['BB_lower'])
        bb_up   = float(current['BB_upper'])
        
        rsi     = float(current['RSI'])
        prev_rsi= float(prev['RSI'])
        
        atr     = float(current['ATR'])
        volume  = float(current['volume'])
        vol_ma  = float(current['VOL_MA'])

        # ════════════════════════════════════════════════════════════════
        # STRATEGI SWING: MEAN REVERSION + MACRO TREND FILTER
        # ════════════════════════════════════════════════════════════════

        # 1. KONDISI LONG (Beli di Harga Diskon saat Uptrend)
        long_conditions = {
            'macro_uptrend' : close > ema200,                # WAJIB: Harga di atas EMA200
            'value_zone_dn' : low <= bb_low,                 # Harga jatuh menyentuh BB Bawah (Murah)
            'rsi_oversold'  : rsi < 35,                      # RSI Jenuh Jual Ekstrim
            'rsi_bounce'    : rsi > prev_rsi,                # RSI mulai menukik naik (Pantulan)
            'volume_spike'  : volume > vol_ma                # Terjadi lonjakan volume (Ada buyer masuk)
        }

        # 2. KONDISI SHORT (Jual di Harga Premium saat Downtrend)
        short_conditions = {
            'macro_downtrend': close < ema200,               # WAJIB: Harga di bawah EMA200
            'value_zone_up'  : high >= bb_up,                # Harga memompa menyentuh BB Atas (Mahal)
            'rsi_overbought' : rsi > 65,                     # RSI Jenuh Beli Ekstrim
            'rsi_reject'     : rsi < prev_rsi,               # RSI mulai menukik turun (Penolakan)
            'volume_spike'   : volume > vol_ma               # Terjadi lonjakan volume (Ada seller masuk)
        }

        is_long  = all(long_conditions.values())
        is_short = all(short_conditions.values())

        if is_long:
            return "buy", close, atr, f"Swing Long | Pantulan BB Bawah (RSI: {rsi:.1f})"
        elif is_short:
            return "sell", close, atr, f"Swing Short | Penolakan BB Atas (RSI: {rsi:.1f})"

        status = f"Mencari Setup Swing | L:{sum(long_conditions.values())}/5 | S:{sum(short_conditions.values())}/5"
        return None, close, atr, status