import numpy as np
from utils.logger import logger

class TrendFollowingStrategy:
    """
    SCALPING ENGINE v2 — Dirancang khusus untuk TF 1m.

    3 Sub-Strategi (salah satu cukup memenuhi syarat untuk entry):
    ─────────────────────────────────────────────────────────────
    A. EMA MOMENTUM CROSS
       Sinyal tercepat. EMA9 cross EMA21 dikonfirmasi arah EMA50.
       Cocok untuk trending market.

    B. MACD SCALP PULL-BACK
       Harga pull-back ke EMA21 saat MACD histogram berbalik arah.
       Sinyal lebih sedikit tapi akurasi lebih tinggi.

    C. BB SQUEEZE BREAKOUT
       Volatilitas rendah (BB width sempit) tiba-tiba meledak dengan
       candle besar + volume. Menangkap awal momentum baru.

    Filter wajib untuk SEMUA strategi:
    - Tidak ada sinyal saat BB terlalu lebar (pasar sudah terlalu volatile)
    - Volume di atas rata-rata (ada likuiditas nyata)
    - Body candle tidak terlalu kecil / bukan doji
    """

    # ── Threshold yang bisa di-tune ──────────────────────────────────────
    RSI_LONG_MAX   = 65   # RSI tidak boleh overbought saat long
    RSI_SHORT_MIN  = 35   # RSI tidak boleh oversold saat short
    RSI_EXTREME_L  = 25   # RSI sangat oversold → overide filter untuk counter-trend
    RSI_EXTREME_S  = 75   # RSI sangat overbought → overide filter untuk counter-trend
    VOL_MIN_RATIO  = 0.4  # Diturunkan: testnet & jam sepi volume memang rendah
    BODY_MIN_RATIO = 0.1  # Diturunkan: filter doji saja, bukan candle kecil
    BB_MAX_WIDTH   = 0.04 # BB width maksimal 4% (filter saat terlalu volatile)
    BB_SQUEEZE_THR = 0.005 # BB width < 0.5% = kondisi squeeze (disesuaikan testnet)

    def _global_filters(self, current, prev):
        """
        Filter yang wajib lolos sebelum strategi apapun dijalankan.
        Log detail alasan kegagalan untuk debugging.
        """
        vol   = float(current['VOL_RATIO'])
        body  = float(current['BODY_RATIO'])
        bbw   = float(current['BB_width'])

        vol_ok  = vol  >= self.VOL_MIN_RATIO
        body_ok = body >= self.BODY_MIN_RATIO
        bb_ok   = bbw  <= self.BB_MAX_WIDTH

        return vol_ok and body_ok and bb_ok

    def _strategy_a_ema_cross(self, current, prev):
        """
        Sub-strategi A: EMA9/EMA21 Momentum Cross
        Kondisi LONG : EMA9 baru saja cross di atas EMA21, harga di atas EMA50
        Kondisi SHORT: EMA9 baru saja cross di bawah EMA21, harga di bawah EMA50
        """
        close   = float(current['close'])
        ema9    = float(current['EMA9'])
        ema21   = float(current['EMA21'])
        ema50   = float(current['EMA50'])
        rsi     = float(current['RSI'])

        prev_ema9  = float(prev['EMA9'])
        prev_ema21 = float(prev['EMA21'])

        # Deteksi crossover (bukan hanya posisi, tapi peristiwa cross)
        cross_up   = (prev_ema9 <= prev_ema21) and (ema9 > ema21)
        cross_down = (prev_ema9 >= prev_ema21) and (ema9 < ema21)

        if cross_up and close > ema50 and rsi < self.RSI_LONG_MAX:
            return "buy", f"EMA Cross Up | EMA9>{ema21:.4f} | RSI:{rsi:.1f}"

        if cross_down and close < ema50 and rsi > self.RSI_SHORT_MIN:
            return "sell", f"EMA Cross Down | EMA9<{ema21:.4f} | RSI:{rsi:.1f}"

        return None, None

    def _strategy_b_macd_pullback(self, current, prev):
        """
        Sub-strategi B: MACD Pull-back ke EMA21
        Harga menyentuh EMA21 (pull-back) saat MACD histogram berbalik positif/negatif.
        Ini menangkap re-entry setelah pull-back dalam trend.
        """
        close      = float(current['close'])
        ema21      = float(current['EMA21'])
        ema50      = float(current['EMA50'])
        macd_hist  = float(current['MACD_hist'])
        prev_hist  = float(prev['MACD_hist'])
        rsi        = float(current['RSI'])
        atr        = float(current['ATR'])

        near_ema21 = abs(close - ema21) <= (atr * 0.5)  # Harga dalam jangkauan 0.5 ATR dari EMA21

        hist_turn_up   = (prev_hist < 0) and (macd_hist > prev_hist)  # Histogram mulai naik dari negatif
        hist_turn_down = (prev_hist > 0) and (macd_hist < prev_hist)  # Histogram mulai turun dari positif

        if near_ema21 and hist_turn_up and close > ema50 and rsi < self.RSI_LONG_MAX:
            return "buy", f"MACD Pull-back | Hist:{macd_hist:.6f} | RSI:{rsi:.1f}"

        if near_ema21 and hist_turn_down and close < ema50 and rsi > self.RSI_SHORT_MIN:
            return "sell", f"MACD Pull-back | Hist:{macd_hist:.6f} | RSI:{rsi:.1f}"

        return None, None

    def _strategy_c_bb_breakout(self, current, prev):
        """
        Sub-strategi C: Bollinger Band Squeeze Breakout
        Volatilitas mengecil (squeeze), lalu harga meledak keluar BB dengan candle besar.
        Menangkap awal impulsive move.
        """
        close     = float(current['close'])
        bb_up     = float(current['BB_upper'])
        bb_low    = float(current['BB_lower'])
        bb_width  = float(current['BB_width'])
        prev_bbw  = float(prev['BB_width'])
        ema50     = float(current['EMA50'])
        rsi       = float(current['RSI'])
        body_r    = float(current['BODY_RATIO'])

        # Squeeze: candle sebelumnya sempit, sekarang melebar
        was_squeeze = prev_bbw < self.BB_SQUEEZE_THR
        expanding   = bb_width > prev_bbw * 1.2  # Width melebar 20%+
        big_candle  = body_r >= 0.8              # Candle besar (bukan doji)

        if was_squeeze and expanding and big_candle:
            if close > bb_up and close > ema50 and rsi < self.RSI_EXTREME_S:
                return "buy", f"BB Breakout Up | Width:{bb_width:.4f} | RSI:{rsi:.1f}"
            if close < bb_low and close < ema50 and rsi > self.RSI_EXTREME_L:
                return "sell", f"BB Breakout Down | Width:{bb_width:.4f} | RSI:{rsi:.1f}"

        return None, None

    def generate_signal(self, df, orderbook=None):
        if df.empty or len(df) < 3:
            return None, None, None, "Data tidak cukup"

        current = df.iloc[-1]
        prev    = df.iloc[-2]

        close = float(current['close'])
        atr   = float(current['ATR'])

        # ── Global filter wajib ───────────────────────────────────────────
        vol  = float(current['VOL_RATIO'])
        bbw  = float(current['BB_width'])
        body = float(current['BODY_RATIO'])

        if not self._global_filters(current, prev):
            reasons = []
            if vol  < self.VOL_MIN_RATIO:  reasons.append(f"VOL:{vol:.2f}x<{self.VOL_MIN_RATIO}")
            if body < self.BODY_MIN_RATIO: reasons.append(f"Body:{body:.2f}<{self.BODY_MIN_RATIO}")
            if bbw  > self.BB_MAX_WIDTH:   reasons.append(f"BB:{bbw:.4f}>{self.BB_MAX_WIDTH}")
            return None, close, atr, f"Filter gagal [{', '.join(reasons)}]"

        # ── Order book filter (jika tersedia) ─────────────────────────────
        if orderbook:
            try:
                bids = orderbook.get('bids', [])
                asks = orderbook.get('asks', [])
                if bids and asks:
                    best_bid = float(bids[0][0])
                    best_ask = float(asks[0][0])
                    spread_pct = (best_ask - best_bid) / best_bid
                    if spread_pct > 0.001:  # Skip jika spread > 0.1%
                        return None, close, atr, f"Spread terlalu lebar: {spread_pct*100:.3f}%"
            except Exception:
                pass

        # ── Jalankan 3 sub-strategi secara prioritas ──────────────────────
        # Prioritas: A (paling sering) → B (medium) → C (paling jarang/kuat)
        for strategy_fn in [
            self._strategy_a_ema_cross,
            self._strategy_b_macd_pullback,
            self._strategy_c_bb_breakout,
        ]:
            signal, reason = strategy_fn(current, prev)
            if signal:
                return signal, close, atr, reason

        # ── Status jika tidak ada sinyal ──────────────────────────────────
        rsi   = float(current['RSI'])
        ema9  = float(current['EMA9'])
        ema21 = float(current['EMA21'])
        gap   = ((ema9 - ema21) / ema21) * 100
        return None, close, atr, f"Standby | RSI:{rsi:.1f} EMA gap:{gap:+.3f}%"
