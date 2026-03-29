import threading
import time
import io
import sqlite3
from datetime import datetime
import telebot
from telebot import types
import mplfinance as mpf
from flask import Flask, jsonify, render_template_string, request
import logging

from config import settings
from config.state import bot_state
from exchange.gateio import GateioExchange
from indicators.indicators import MarketIndicators
from strategies.strategy import TrendFollowingStrategy
from risk_management.risk import RiskManager
from utils.logger import logger, send_telegram_alert

bot = telebot.TeleBot(settings.TG_TOKEN)

# ==========================================
# DATABASE MANAGER (SQLITE)
# ==========================================
DB_NAME = "hedgefund_trade_history.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS closed_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            entry_price REAL,
            close_price REAL,
            contracts REAL,
            realized_pnl REAL,
            fee REAL,
            net_pnl REAL,
            timestamp DATETIME DEFAULT (STRFTIME('%Y-%m-%d %H:%M:%S', 'NOW', 'localtime'))
        )
    """)
    conn.commit()
    conn.close()

def record_closed_trade(symbol, side, entry_price, close_price, contracts, realized_pnl, fee, net_pnl):
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO closed_trades 
            (symbol, side, entry_price, close_price, contracts, realized_pnl, fee, net_pnl)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (symbol, side, entry_price, close_price, contracts, realized_pnl, fee, net_pnl))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Gagal merekam trade ke DB: {e}")

# ==========================================
# GLOBAL STATE UNTUK WEB DASHBOARD
# ==========================================
dashboard_data = {
    'balance': 0.0,
    'total_floating_pnl': 0.0,
    'total_realized_pnl': 0.0,
    'win_rate_percent': 0.0,
    'pnl_percent': 0.0,
    'positions': [],
    'status': 'STOPPED',
    'last_update': '-'
}

# ==========================================
# WEB DASHBOARD SERVER (FLASK)
# ==========================================
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)
app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>HEDGEFUND QUANT ENGINE V3.3</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { background-color: #0f172a; color: #e2e8f0; font-family: 'Inter', system-ui, -apple-system, sans-serif; }
        .card { background-color: #1e293b; border: 1px solid #334155; }
        .text-green { color: #22c55e; }
        .text-red { color: #ef4444; }
        .tab-btn.active { background-color: #3b82f6; color: #fff; }
    </style>
</head>
<body class="p-4 md:p-6 lg:p-8">
    <div class="max-w-7xl mx-auto">
        <div class="flex justify-between items-center mb-8 border-b border-slate-700 pb-4">
            <h1 class="text-3xl font-extrabold tracking-tight text-slate-100"> GATE.IO BOT(Testnet) <span class="text-xs text-blue-500">V3.3 (Equity Curve Fix)</span></h1>
            <div class="text-right flex items-center gap-2 card p-2 px-3 rounded-full text-sm">
                <span id="engine-status" class="font-bold">-</span>
                <span class="text-slate-500">| Panel Live: <span id="last-update" class="font-mono text-slate-300">-</span></span>
            </div>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
            <div class="card p-6 rounded-xl shadow-2xl">
                <h2 class="text-slate-400 text-sm mb-1 uppercase tracking-widest font-semibold">Live Balance (USDT)</h2>
                <p id="balance" class="text-4xl font-extrabold">0.00</p>
            </div>
            <div class="card p-6 rounded-xl shadow-2xl">
                <h2 class="text-slate-400 text-sm mb-1 uppercase tracking-widest font-semibold">Total Floating PnL (USDT)</h2>
                <p id="total-pnl" class="text-4xl font-extrabold">0.00</p>
            </div>
            <div class="card p-6 rounded-xl shadow-2xl">
                <h2 class="text-slate-400 text-sm mb-1 uppercase tracking-widest font-semibold">Total Net PnL (USDT)</h2>
                <p id="total-realized-pnl" class="text-4xl font-extrabold text-slate-100">0.00</p>
            </div>
            <div class="card p-6 rounded-xl shadow-2xl">
                <h2 class="text-slate-400 text-sm mb-1 uppercase tracking-widest font-semibold">Historical Win Rate (%)</h2>
                <p id="win-rate" class="text-4xl font-extrabold text-blue-500">0%</p>
            </div>
        </div>

        <div class="grid grid-cols-1 xl:grid-cols-3 gap-8">
            <div class="xl:col-span-2 space-y-8">
                <div>
                    <h2 class="text-xl font-bold mb-4 border-b border-slate-700 pb-2 flex justify-between items-center">
                        Active Trades (<span id="pos-count">0</span>/{{ max_pos }})
                        <span class="text-xs text-red-500 font-normal">Panel Live: Update Ultra-Cepat 100ms</span>
                    </h2>
                    <div class="overflow-x-auto card rounded-xl shadow-2xl">
                        <table class="w-full text-left border-collapse min-w-[600px]">
                            <thead>
                                <tr class="bg-slate-800 text-slate-300 text-xs uppercase tracking-wider">
                                    <th class="p-4 border-b border-slate-700">Crypto</th>
                                    <th class="p-4 border-b border-slate-700">Side</th>
                                    <th class="p-4 border-b border-slate-700">Entry</th>
                                    <th class="p-4 border-b border-slate-700">Size (USDT)</th>
                                    <th class="p-4 border-b border-slate-700">Floating PnL</th>
                                    <th class="p-4 border-b border-slate-700">PnL %</th>
                                </tr>
                            </thead>
                            <tbody id="positions-table">
                            </tbody>
                        </table>
                    </div>
                </div>
                
                <div class="card p-6 rounded-xl min-h-[350px] shadow-2xl relative">
                    <h2 class="text-slate-400 text-sm mb-4 uppercase tracking-widest font-semibold">Trade-by-Trade Equity Curve</h2>
                    <div class="absolute inset-0 p-6 pt-12">
                        <canvas id="pnlHistoryChart"></canvas>
                    </div>
                </div>
            </div>

            <div class="space-y-6">
                <div class="flex justify-between items-center border-b border-slate-700 pb-2">
                    <h2 class="text-xl font-bold">Trade History</h2>
                    <div class="flex gap-2 text-xs">
                        <button onclick="setHistoryFilter('hourly')" class="tab-btn active px-3 py-1.5 rounded-full card hover:bg-slate-800 transition" id="btn-hourly">Hourly</button>
                        <button onclick="setHistoryFilter('daily')" class="tab-btn px-3 py-1.5 rounded-full card hover:bg-slate-800 transition" id="btn-daily">Daily</button>
                        <button onclick="setHistoryFilter('monthly')" class="tab-btn px-3 py-1.5 rounded-full card hover:bg-slate-800 transition" id="btn-monthly">Monthly</button>
                    </div>
                </div>
                <div class="space-y-3 max-h-[600px] overflow-y-auto pr-2" id="history-list">
                </div>
            </div>
        </div>
    </div>

    <script>
        let pnlChart = null;

        function updateDashboardLive() {
            const timestamp = new Date().getTime();
            fetch('/api/data?t=' + timestamp)
                .then(response => response.json())
                .then(data => {
                    document.getElementById('balance').innerText = data.balance.toFixed(2);
                    
                    const pnlEl = document.getElementById('total-pnl');
                    pnlEl.innerText = (data.total_floating_pnl > 0 ? '+' : '') + data.total_floating_pnl.toFixed(4);
                    pnlEl.className = 'text-4xl font-extrabold ' + (data.total_floating_pnl > 0 ? 'text-green' : (data.total_floating_pnl < 0 ? 'text-red' : 'text-slate-100'));

                    const statusEl = document.getElementById('engine-status');
                    statusEl.innerText = data.status;
                    statusEl.className = 'font-bold text-lg ' + (data.status === 'RUNNING' ? 'text-green' : 'text-red');

                    document.getElementById('pos-count').innerText = data.positions.length;
                    document.getElementById('last-update').innerText = data.last_update;

                    let tableHtml = '';
                    if (data.positions.length === 0) {
                        tableHtml = '<tr><td colspan="6" class="p-4 text-center text-slate-500">No active positions. Scanning market...</td></tr>';
                    } else {
                        data.positions.forEach(p => {
                            const pnlColor = p.pnl > 0 ? 'text-green' : (p.pnl < 0 ? 'text-red' : 'text-slate-100');
                            const sideColor = p.side === 'BUY' ? 'text-green' : 'text-red';
                            const sideText = p.side === 'BUY' ? 'LONG 📈' : 'SHORT 📉';
                            const coinName = p.symbol.split('/')[0];

                            tableHtml += `
                                <tr class="hover:bg-slate-800 transition-colors border-b border-slate-700">
                                    <td class="p-4 font-bold text-slate-100">${coinName}</td>
                                    <td class="p-4 ${sideColor}">${sideText}</td>
                                    <td class="p-4">${p.entry.toFixed(4)}</td>
                                    <td class="p-4 font-mono text-slate-300">${p.size_usdt.toFixed(2)}</td>
                                    <td class="p-4 font-bold ${pnlColor}">${(p.pnl > 0 ? '+' : '') + p.pnl.toFixed(4)}</td>
                                    <td class="p-4 font-bold ${pnlColor}">${(p.pnl_pct > 0 ? '+' : '') + p.pnl_pct.toFixed(2)}%</td>
                                </tr>
                            `;
                        });
                    }
                    document.getElementById('positions-table').innerHTML = tableHtml;
                })
                .catch(err => console.error('Error fetching data:', err));
        }

        let currentFilter = 'hourly';
        function setHistoryFilter(filter) {
            currentFilter = filter;
            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            document.getElementById('btn-' + filter).classList.add('active');
            updateHistory();
        }

        function renderChart(rawChartData) {
            // FIX: Tambahkan titik awal 0 agar garis mulai dari dasar
            const labels = ['Start', ...rawChartData.map(d => d.time)];
            
            let cumProfit = [0];
            let cumLoss = [0];
            let cp = 0; let cl = 0;

            rawChartData.forEach(d => {
                if (d.pnl > 0) {
                    cp += d.pnl;
                } else {
                    cl += Math.abs(d.pnl);
                }
                cumProfit.push(cp);
                cumLoss.push(cl);
            });

            if (pnlChart) {
                pnlChart.data.labels = labels;
                pnlChart.data.datasets[0].data = cumProfit;
                pnlChart.data.datasets[1].data = cumLoss;
                pnlChart.update();
            } else {
                const ctx = document.getElementById('pnlHistoryChart').getContext('2d');
                pnlChart = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: labels,
                        datasets: [
                            {
                                label: 'Gross Profit (Cumulative)',
                                data: cumProfit,
                                borderColor: '#22c55e',
                                backgroundColor: 'rgba(34, 197, 94, 0.15)',
                                fill: true,
                                tension: 0.3,
                                borderWidth: 3,
                                pointRadius: 3
                            },
                            {
                                label: 'Gross Loss (Cumulative)',
                                data: cumLoss,
                                borderColor: '#ef4444',
                                backgroundColor: 'rgba(239, 68, 68, 0.15)',
                                fill: true,
                                tension: 0.3,
                                borderWidth: 3,
                                pointRadius: 3
                            }
                        ]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        color: '#94a3b8',
                        scales: {
                            x: { grid: { color: '#334155' }, ticks: { color: '#94a3b8', maxTicksLimit: 10 } },
                            y: { grid: { color: '#334155' }, ticks: { color: '#94a3b8' } }
                        },
                        plugins: { legend: { labels: { color: '#e2e8f0' } } }
                    }
                });
            }
        }

        function updateHistory() {
            const timestamp = new Date().getTime();
            fetch(`/api/history?filter=${currentFilter}&t=${timestamp}`)
                .then(response => response.json())
                .then(data => {
                    document.getElementById('total-realized-pnl').innerText = (data.total_realized_pnl > 0 ? '+' : '') + data.total_realized_pnl.toFixed(4);
                    document.getElementById('win-rate').innerText = data.win_rate_percent.toFixed(1) + '%';
                    document.getElementById('total-realized-pnl').className = 'text-4xl font-extrabold ' + (data.total_realized_pnl > 0 ? 'text-green' : (data.total_realized_pnl < 0 ? 'text-red' : 'text-slate-100'));
                    
                    let historyHtml = '';
                    if (data.history.length === 0) {
                        historyHtml = '<div class="text-center text-slate-500 py-10">Belum ada trade tertutup.</div>';
                    } else {
                        data.history.forEach(item => {
                            const pnlColor = item.pnl > 0 ? 'text-green' : (item.pnl < 0 ? 'text-red' : 'text-slate-100');
                            const icon = item.pnl > 0 ? '🟢' : (item.pnl < 0 ? '🛑' : '⚪');
                            historyHtml += `
                                <div class="card p-4 rounded-xl shadow flex items-center justify-between gap-4">
                                    <div class="flex items-center gap-3">
                                        <div class="text-xl">${icon}</div>
                                        <div>
                                            <p class="font-bold text-slate-100 font-mono tracking-tight">${item.period}</p>
                                            <p class="text-xs text-slate-500">${item.trades} trades</p>
                                        </div>
                                    </div>
                                    <div class="text-right">
                                        <p class="font-extrabold text-lg ${pnlColor}">${(item.pnl > 0 ? '+' : '') + item.pnl.toFixed(4)} <span class="text-xs">USDT</span></p>
                                        <p class="text-xs text-slate-500">Net PnL</p>
                                    </div>
                                </div>
                            `;
                        });
                    }
                    document.getElementById('history-list').innerHTML = historyHtml;
                    
                    // Render Chart menggunakan raw data (trade per trade) bukan data rekap
                    renderChart(data.chart_raw_data);
                })
                .catch(err => console.error('Error fetching history:', err));
        }

        setInterval(updateDashboardLive, 100); 
        updateDashboardLive();
        setInterval(updateHistory, 5000); 
        updateHistory();
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, max_pos=settings.MAX_POSITIONS)

@app.route('/api/data')
def api_data():
    return jsonify(dashboard_data)

@app.route('/api/history')
def api_history():
    period_filter = request.args.get('filter', 'hourly')
    
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 1. Kalkulasi Total
    cursor.execute("SELECT net_pnl FROM closed_trades")
    all_pnls = [row[0] for row in cursor.fetchall()]
    total_r_pnl = sum(all_pnls)
    
    total_trades = len(all_pnls)
    won_trades = sum(1 for pnl in all_pnls if pnl > 0)
    win_rate = (won_trades / total_trades * 100) if total_trades > 0 else 0
    
    # 2. Rekap Data untuk Tabel/List (Dikelompokkan)
    history_pnls = []
    if period_filter == 'hourly':
        sql = "SELECT STRFTIME('%Y-%m-%d %H:00', timestamp) as period, COUNT(*) as trades, SUM(net_pnl) as pnl FROM closed_trades GROUP BY period ORDER BY period DESC LIMIT 100"
    elif period_filter == 'daily':
        sql = "SELECT STRFTIME('%Y-%m-%d', timestamp) as period, COUNT(*) as trades, SUM(net_pnl) as pnl FROM closed_trades GROUP BY period ORDER BY period DESC LIMIT 100"
    else:
        sql = "SELECT STRFTIME('%Y-%m', timestamp) as period, COUNT(*) as trades, SUM(net_pnl) as pnl FROM closed_trades GROUP BY period ORDER BY period DESC LIMIT 100"

    cursor.execute(sql)
    for row in cursor.fetchall():
        history_pnls.append({
            'period': row['period'],
            'trades': row['trades'],
            'pnl':    row['pnl']
        })

    # 3. FIX: Ambil Raw Data Trade-by-Trade khusus untuk dirender di Chart agar melengkung sempurna
    cursor.execute("SELECT STRFTIME('%H:%M:%S', timestamp) as time_label, net_pnl FROM closed_trades ORDER BY id ASC LIMIT 200")
    chart_raw_data = [{'time': r['time_label'], 'pnl': r['net_pnl']} for r in cursor.fetchall()]

    conn.close()
        
    return jsonify({
        'total_realized_pnl': total_r_pnl,
        'win_rate_percent': win_rate,
        'history': history_pnls,
        'chart_raw_data': chart_raw_data
    })

def run_flask():
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

# ==========================================
# MULTI-PAIR POSITION MONITOR (FIXED PNL)
# ==========================================
def monitor_positions_for_alerts(ex, positions_before: list) -> list:
    positions_now = ex.get_all_open_positions()

    symbols_before = {p.get('symbol') for p in positions_before}
    symbols_now    = {p.get('symbol') for p in positions_now}
    closed_symbols = symbols_before - symbols_now

    if closed_symbols:
        for sym in closed_symbols:
            p = next((x for x in positions_before if x.get('symbol') == sym), None)
            if not p: continue

            side        = p.get('side', '-').upper()
            entry_price = float(p.get('entryPrice') or p.get('entry_price') or 0)
            contracts   = float(p.get('contracts') or 0)
            unrealized  = float(p.get('unrealizedPnl') or p.get('unrealised_pnl') or 0)

            closed_info = ex.get_last_closed_pnl(sym)

            if closed_info:
                realized_pnl = closed_info['realized_pnl']
                fee          = closed_info['fee']
                close_price  = closed_info['close_price']
                
                if realized_pnl == 0.0 and close_price > 0 and entry_price > 0:
                    try:
                        c_size = ex.get_market_info(sym).get('contract_size', 1)
                        if side == 'BUY':
                            realized_pnl = (close_price - entry_price) * contracts * c_size
                        else:
                            realized_pnl = (entry_price - close_price) * contracts * c_size
                    except Exception as e:
                        logger.error(f"Gagal hitung manual PnL: {e}")

                net_pnl = realized_pnl - fee
            else:
                realized_pnl = unrealized
                net_pnl      = unrealized
                fee          = 0
                close_price  = 0
            
            record_closed_trade(sym, side, entry_price, close_price, contracts, realized_pnl, fee, net_pnl)

            if net_pnl > 0:
                trigger_label, pnl_emoji = "✅ TAKE PROFIT TERPICU", "🟢"
            elif net_pnl < 0:
                trigger_label, pnl_emoji = "🛑 STOP LOSS TERPICU", "🔴"
            else:
                trigger_label, pnl_emoji = "📌 POSISI DITUTUP", "⚪"

            send_telegram_alert(
                f"{trigger_label}\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"Pair   : <code>{sym}</code>\n"
                f"Sisi   : <b>{'LONG 📈' if side == 'BUY' else 'SHORT 📉'}</b>\n"
                f"Entry  : <code>{entry_price:.4f}</code>\n"
                f"Close  : <code>{close_price:.4f}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"{pnl_emoji} Net PnL : <b>{net_pnl:+.4f} USDT</b>"
            )

    return positions_now

# ==========================================
# BACKGROUND DATA UPDATER (WEB DASHBOARD)
# ==========================================
def dashboard_updater_loop():
    ex = GateioExchange()
    try:
        ex.exchange.load_markets()
    except Exception:
        pass

    while True:
        try:
            if bot_state.running:
                current_balance = ex.get_balance()
                open_positions = ex.get_all_open_positions()
                
                total_floating_unrealized = 0
                pos_list = []
                
                for p in open_positions:
                    sym = p.get('symbol', '')
                    side = p.get('side', '-').upper()
                    entry = float(p.get('entryPrice') or 0)
                    contracts = float(p.get('contracts') or 0)
                    pnl = float(p.get('unrealizedPnl') or p.get('unrealised_pnl') or 0)
                    total_floating_unrealized += pnl

                    c_size = float(ex.exchange.markets.get(sym, {}).get('contractSize', 0.0001)) if ex.exchange.markets else 0.0001
                    size_usdt = contracts * c_size * entry

                    leverage = bot_state.leverage
                    margin_used = size_usdt / leverage if leverage else size_usdt
                    pnl_pct = (pnl / margin_used * 100) if margin_used > 0 else 0

                    pos_list.append({
                        'symbol': sym,
                        'side': side,
                        'entry': entry,
                        'size_usdt': size_usdt,
                        'pnl': pnl,
                        'pnl_pct': pnl_pct
                    })
                
                dashboard_data['balance'] = current_balance
                dashboard_data['total_floating_pnl'] = total_floating_unrealized
                dashboard_data['pnl_percent'] = (total_floating_unrealized / current_balance * 100) if current_balance > 0 else 0
                dashboard_data['positions'] = pos_list
                
            dashboard_data['status'] = 'RUNNING' if bot_state.running else 'STOPPED'
            dashboard_data['last_update'] = datetime.now().strftime("%H:%M:%S.%f")[:-3] 
            
            time.sleep(0.3) 
        except Exception as e:
            time.sleep(2)

# ==========================================
# TRADING ENGINE (FAST SCALPING MODE)
# ==========================================
def trading_loop():
    ex    = GateioExchange()
    ind   = MarketIndicators()
    strat = TrendFollowingStrategy()
    risk  = RiskManager(ex)

    tracked_positions = ex.get_all_open_positions()

    while True:
        if not bot_state.running:
            time.sleep(5)
            continue

        try:
            state = bot_state.get_snapshot()
            
            if state['settings_changed']:
                for sym in settings.SYMBOLS:
                    ex.apply_account_settings(sym, state['leverage'], state['margin_mode'])
                bot_state.mark_settings_applied()

            tracked_positions = monitor_positions_for_alerts(ex, tracked_positions)
            tracked_symbols = [p.get('symbol') for p in tracked_positions]

            if len(tracked_positions) >= settings.MAX_POSITIONS:
                time.sleep(5)
                continue

            for symbol in settings.SYMBOLS:
                if symbol in tracked_symbols:
                    continue
                
                df = ex.get_ohlcv(symbol, settings.TIMEFRAME)
                df = ind.apply_indicators(df)
                ob = ex.get_orderbook(symbol)

                signal, price, atr, analysis_txt = strat.generate_signal(df, ob)

                if signal:
                    sl, tp = risk.calculate_sl_tp(signal, price, atr)
                    size   = risk.calculate_position_size(symbol, price, sl, state['risk_per_trade'])

                    if size > 0:
                        order = ex.create_order(symbol, 'market', signal, size)
                        if order:
                            ex.create_sl_tp_orders(symbol, signal, size, sl, tp)
                            notional = size * ex.get_market_info(symbol)['contract_size'] * price

                            send_telegram_alert(
                                f"🚀 <b>FAST SCALP MASUK</b>\n"
                                f"Pair : <code>{symbol}</code>\n"
                                f"Tipe : <b>{'LONG 📈' if signal == 'buy' else 'SHORT 📉'}</b>\n"
                                f"Size : {size} (Notional {notional:.2f} USDT)\n"
                                f"🛑 SL: {sl:.4f} | ✅ TP: {tp:.4f}"
                            )
                            tracked_positions = ex.get_all_open_positions()
                            tracked_symbols = [p.get('symbol') for p in tracked_positions]
                            
                            if len(tracked_positions) >= settings.MAX_POSITIONS:
                                break 
                            time.sleep(2) 

            time.sleep(5) 
            
        except Exception as e:
            logger.error(f"Error di Trading Loop: {e}")
            time.sleep(5)

# ==========================================
# TELEGRAM UI & PANEL CONTROLLER
# ==========================================
def main_menu():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(
        types.KeyboardButton('▶️ Start Bot'),
        types.KeyboardButton('⏸️ Stop Bot'),
        types.KeyboardButton('⚙️ Status Engine')
    )
    return markup

@bot.message_handler(func=lambda message: message.text == '▶️ Start Bot' or message.text == '/start_bot')
def cmd_start(message):
    bot_state.start()
    bot.reply_to(message, "🟢 <b>BOT STARTED (SCALPING MODE)</b>", reply_markup=main_menu(), parse_mode="HTML")

@bot.message_handler(func=lambda message: message.text == '⏸️ Stop Bot' or message.text == '/stop_bot')
def cmd_stop(message):
    bot_state.stop()
    bot.reply_to(message, "🔴 <b>BOT STOPPED</b>", reply_markup=main_menu(), parse_mode="HTML")

@bot.message_handler(func=lambda message: message.text == '⚙️ Status Engine' or message.text == '/status')
def cmd_status(message):
    state = bot_state.get_snapshot()
    status_label = "🟢 RUNNING" if state['is_running'] else "🔴 STOPPED"
    bot.reply_to(
        message, 
        f"⚙️ <b>ENGINE STATUS</b>\n"
        f"State: {status_label}\n"
        f"TF   : <b>{settings.TIMEFRAME}</b>\n"
        f"🌐 <b>Web Panel:</b> <code>http://127.0.0.1:5000</code>", 
        parse_mode="HTML", reply_markup=main_menu()
    )

if __name__ == "__main__":
    init_db()

    t_web = threading.Thread(target=run_flask)
    t_web.daemon = True
    t_web.start()

    t_dash_updater = threading.Thread(target=dashboard_updater_loop)
    t_dash_updater.daemon = True
    t_dash_updater.start()

    t_trade = threading.Thread(target=trading_loop)
    t_trade.daemon = True
    t_trade.start()

    send_telegram_alert(
        f"🔌 <b>TEST SCALPING BOT ONLINE (V3.3)</b>\n"
        f"Timeframe: <b>{settings.TIMEFRAME}</b>\n"
        f"🌐 Web: <code>http://127.0.0.1:5000</code>"
    )
    bot.infinity_polling()