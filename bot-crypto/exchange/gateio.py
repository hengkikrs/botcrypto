import ccxt
import pandas as pd
import re
from config import settings
from config.state import bot_state
from utils.logger import logger

class GateioExchange:
    def __init__(self):
        self.exchange = ccxt.gateio({
            'apiKey': settings.API_KEY,
            'secret': settings.API_SECRET,
            'enableRateLimit': True,
            'options': {'defaultType': 'swap'}
        })
        if settings.MODE == "PAPER":
            self.exchange.set_sandbox_mode(True)

        try:
            self.exchange.load_markets()
        except Exception as e:
            logger.error(f"Gagal memuat market: {e}")

    def apply_account_settings(self, symbol, leverage, margin_mode):
        target_leverage = leverage
        max_attempts    = 3

        for attempt in range(max_attempts):
            try:
                self.exchange.set_leverage(target_leverage, symbol)
                logger.info(f"✅ Leverage berhasil diset ke {target_leverage}x untuk {symbol}")
                bot_state.leverage = target_leverage
                break
            except Exception as e:
                error_msg  = str(e)
                max_allowed = None

                match1 = re.search(r'between 1 and (\d+)', error_msg)
                match2 = re.search(r'limit \[1,\s*(\d+)\]', error_msg)

                if match2:
                    max_allowed = int(match2.group(1))
                elif match1:
                    max_allowed = int(match1.group(1))

                if max_allowed and max_allowed < target_leverage:
                    logger.warning(
                        f"⚠️ Leverage {target_leverage}x ditolak untuk {symbol}. "
                        f"Mencoba batas API: {max_allowed}x"
                    )
                    target_leverage = max_allowed
                else:
                    logger.warning(f"Leverage warning {symbol}: {e}")
                    break

    def get_market_info(self, symbol):
        try:
            market           = self.exchange.market(symbol)
            min_amount       = float(market.get('limits', {}).get('amount', {}).get('min', 1))
            amount_precision = int(market.get('precision', {}).get('amount', 0))
            contract_size    = float(market.get('contractSize', 0.0001))
            return {
                'min_amount':       min_amount,
                'amount_precision': amount_precision,
                'contract_size':    contract_size
            }
        except Exception as e:
            logger.warning(f"get_market_info fallback untuk {symbol}: {e}")
            return {'min_amount': 1, 'amount_precision': 0, 'contract_size': 0.0001}

    def get_ohlcv(self, symbol, timeframe, limit=300):
        try:
            bars = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            df   = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except Exception as e:
            logger.error(f"get_ohlcv gagal untuk {symbol}: {e}")
            return pd.DataFrame()

    def get_orderbook(self, symbol, limit=20):
        try:
            return self.exchange.fetch_order_book(symbol, limit=limit)
        except Exception as e:
            logger.warning(f"get_orderbook gagal untuk {symbol}: {e}")
            return None

    def get_balance(self):
        try:
            balance = self.exchange.fetch_balance(params={'type': 'swap'})
            return float(balance.get('USDT', {}).get('free', 0))
        except Exception as e:
            logger.error(f"get_balance gagal: {e}")
            return 0.0

    def get_all_open_positions(self):
        try:
            positions = self.exchange.fetch_positions()
            return [p for p in positions if abs(float(p.get('contracts', 0))) > 0]
        except Exception as e:
            logger.error(f"get_all_open_positions gagal: {e}")
            return []

    def get_last_closed_pnl(self, symbol):
        try:
            trades = self.exchange.fetch_my_trades(symbol, limit=10)
            if trades:
                for trade in reversed(trades):
                    info         = trade.get('info', {})
                    realized_pnl = float(
                        info.get('realised_pnl') or info.get('realisedPnl') or
                        info.get('close_profit') or info.get('closePnl') or
                        info.get('pnl') or 0
                    )
                    fee         = float(trade.get('fee', {}).get('cost', 0) or 0)
                    close_price = float(trade.get('price', 0))
                    side        = str(trade.get('side', '-')).upper()
                    if close_price > 0:
                        return {
                            'realized_pnl': realized_pnl,
                            'fee':          fee,
                            'net_pnl':      realized_pnl - fee,
                            'close_price':  close_price,
                            'side':         side,
                        }
            return None
        except Exception as e:
            logger.warning(f"get_last_closed_pnl gagal untuk {symbol}: {e}")
            return None

    def create_order(self, symbol, order_type, side, amount):
        try:
            return self.exchange.create_order(symbol, order_type, side, amount)
        except Exception as e:
            logger.error(f"Gagal eksekusi order {symbol} {side} {amount}: {e}")
            return None

    def create_sl_tp_orders(self, symbol, side, size, sl_price, tp_price):
        """
        FIX: SL dan TP tidak lagi silent fail.
        Setiap kegagalan di-log dan dikembalikan sebagai status.
        """
        close_side = 'sell' if side == 'buy' else 'buy'
        sl_ok = False
        tp_ok = False

        # ── Stop Loss ─────────────────────────────────────────────────────
        try:
            self.exchange.create_order(
                symbol, 'stop', close_side, size,
                price=sl_price,
                params={'stopPrice': sl_price, 'reduceOnly': True}
            )
            sl_ok = True
            logger.info(f"✅ SL ditempatkan: {symbol} @ {sl_price}")
        except Exception as e:
            logger.error(f"❌ GAGAL menempatkan SL untuk {symbol} @ {sl_price}: {e}")

        # ── Take Profit ───────────────────────────────────────────────────
        try:
            self.exchange.create_order(
                symbol, 'limit', close_side, size,
                price=tp_price,
                params={'reduceOnly': True}
            )
            tp_ok = True
            logger.info(f"✅ TP ditempatkan: {symbol} @ {tp_price}")
        except Exception as e:
            logger.error(f"❌ GAGAL menempatkan TP untuk {symbol} @ {tp_price}: {e}")

        return sl_ok, tp_ok
