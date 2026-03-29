import pandas as pd
import numpy as np
import ta

class MarketIndicators:
    @staticmethod
    def apply_indicators(df):
        if df.empty:
            return df

        # ── Macro Trend ───────────────────────────────────────────────────
        df['EMA200'] = ta.trend.ema_indicator(df['close'], window=200)
        
        # ── Short Trend ───────────────────────────────────────────────────
        df['EMA9']  = ta.trend.ema_indicator(df['close'], window=9)
        df['EMA21'] = ta.trend.ema_indicator(df['close'], window=21)

        # ── Momentum & Volatility ─────────────────────────────────────────
        df['RSI'] = ta.momentum.rsi(df['close'], window=14)
        df['ATR'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=14)

        # ── Value Area (Bollinger Bands) ──────────────────────────────────
        bb = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2)
        df['BB_upper'] = bb.bollinger_hband()
        df['BB_lower'] = bb.bollinger_lband()
        df['BB_mid']   = bb.bollinger_mavg()

        # ── Volume ────────────────────────────────────────────────────────
        df['VOL_MA'] = df['volume'].rolling(window=20).mean()

        # Optimasi memory multi-pair
        df = df.iloc[-50:].reset_index(drop=True)
        required_cols = ['EMA200', 'EMA9', 'EMA21', 'RSI', 'ATR', 'BB_upper', 'BB_lower', 'BB_mid', 'VOL_MA']
        df = df.dropna(subset=required_cols)

        return df