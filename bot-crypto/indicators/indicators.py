import pandas as pd
import numpy as np
import ta

class MarketIndicators:
    @staticmethod
    def apply_indicators(df):
        if df.empty or len(df) < 50:
            return pd.DataFrame()

        # ── Macro Trend ───────────────────────────────────────────────────
        # FIX: EMA50 menggantikan EMA200 untuk TF 1m (200 candle = 3.3 jam,
        # terlalu lambat untuk scalping. EMA50 = 50 menit, lebih relevan)
        df['EMA50'] = ta.trend.ema_indicator(df['close'], window=50)

        # ── Short Trend (Scalp Signal) ────────────────────────────────────
        df['EMA9']  = ta.trend.ema_indicator(df['close'], window=9)
        df['EMA21'] = ta.trend.ema_indicator(df['close'], window=21)

        # ── Momentum ─────────────────────────────────────────────────────
        # RSI window 7 lebih responsif untuk scalping 1m vs window 14
        df['RSI']    = ta.momentum.rsi(df['close'], window=7)
        df['RSI_14'] = ta.momentum.rsi(df['close'], window=14)

        # ── MACD — konfirmasi momentum crossover ─────────────────────────
        macd = ta.trend.MACD(df['close'], window_slow=26, window_fast=12, window_sign=9)
        df['MACD']        = macd.macd()
        df['MACD_signal'] = macd.macd_signal()
        df['MACD_hist']   = macd.macd_diff()

        # ── Volatilitas ───────────────────────────────────────────────────
        df['ATR'] = ta.volatility.average_true_range(
            df['high'], df['low'], df['close'], window=7
        )

        # ── Bollinger Bands ───────────────────────────────────────────────
        bb = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2)
        df['BB_upper'] = bb.bollinger_hband()
        df['BB_lower'] = bb.bollinger_lband()
        df['BB_mid']   = bb.bollinger_mavg()
        df['BB_width'] = (df['BB_upper'] - df['BB_lower']) / df['BB_mid']

        # ── Volume ────────────────────────────────────────────────────────
        df['VOL_MA']    = df['volume'].rolling(window=20).mean()
        df['VOL_RATIO'] = df['volume'] / df['VOL_MA']

        # ── Candle Pattern ────────────────────────────────────────────────
        # Body size relatif terhadap ATR — filter candle kecil/doji
        df['BODY']      = abs(df['close'] - df['open'])
        df['BODY_RATIO'] = df['BODY'] / (df['ATR'] + 1e-9)

        # ── FIX: Potong window SETELAH semua indikator dihitung ───────────
        required_cols = [
            'EMA50', 'EMA9', 'EMA21',
            'RSI', 'RSI_14',
            'MACD', 'MACD_signal', 'MACD_hist',
            'ATR', 'BB_upper', 'BB_lower', 'BB_mid', 'BB_width',
            'VOL_MA', 'VOL_RATIO', 'BODY_RATIO'
        ]
        df = df.dropna(subset=required_cols)
        df = df.iloc[-30:].reset_index(drop=True)

        return df
