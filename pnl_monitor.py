# pnl_monitor.py
import ccxt
import pandas as pd
import json
import os
import time
import threading
import logging
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, render_template_string

logger = logging.getLogger("pnl_monitor")

PNL_BP = Blueprint('pnl', __name__)
JSON_FILE = "/tmp/pnl_history.json"  # ← безопасно для Render

def fetch_closed_pnl(api_key, secret, use_demo=False, symbols=None):
    """
    Берём fetch_my_trades() ПО СИМВОЛУ и фильтруем reduceOnly = True
    symbols: список строк, например ['BTC-USDT', ...]
    """
    if symbols is None:
        symbols = ['BTC-USDT']  # fallback

    all_trades = []
    try:
        exchange = ccxt.bingx({
            'apiKey': api_key,
            'secret': secret,
            'options': {'defaultType': 'swap'},
            'enableRateLimit': True,
        })
        if use_demo:
            exchange.set_sandbox_mode(True)

        since = exchange.parse8601((datetime.utcnow() - timedelta(days=7)).isoformat())
        for sym in symbols:
            try:
                trades = exchange.fetch_my_trades(sym, since=since)
                all_trades.extend([t for t in trades if t.get('info', {}).get('reduceOnly') is True])
            except Exception as e:
                logger.warning(f"Нет trades {sym}: {e}")

        df = pd.DataFrame(all_trades)
        if df.empty:
            return pd.DataFrame(columns=['timestamp', 'symbol', 'income', 'balance'])

        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df['price'] = pd.to_numeric(df['price'])
        df['amount'] = pd.to_numeric(df['amount'])
        # доход = (sell - buy) * amount
        df['income'] = (df['side'] == 'sell').astype(int) * df['price'] * df['amount'] - \
                       (df['side'] == 'buy').astype(int) * df['price'] * df['amount']
        df = df[['timestamp', 'symbol', 'income']].sort_values('timestamp')
        df['balance'] = df['income'].cumsum()
        return df
    except Exception as e:
        logger.error(f"fetch_closed_pnl: {e}")
        return pd.DataFrame()

def calc_stats(df: pd.DataFrame) -> dict:
    if df.empty:
        return {
            'equity': [100.0],
            'drawdown': [0.0],
            'max_dd': 0.0,
            'sharpe': 0.0,
            'total_pnl': 0.0,
            'updated': datetime.utcnow().isoformat()
        }

    equity = df['balance'].tolist()
    peak = pd.Series(equity).cummax()
    drawdown = ((pd.Series(equity) - peak) / peak * 100).tolist()
    max_dd = max(drawdown) if drawdown else 0.0
    returns = pd.Series(equity).pct_change().dropna()
    sharpe = returns.mean() / returns.std() * (365**0.5) if returns.std() else 0.0

    return {
        'equity': equity,
        'drawdown': drawdown,
        'max_dd': round(max_dd, 2),
        'sharpe': round(sharpe, 2),
        'total_pnl': round(equity[-1] - 100.0, 4),
        'updated': datetime.utcnow().isoformat()
    }

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>PnL & Drawdown</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>body{font-family:Arial;margin:40px;}</style>
</head>
<body>
    <h2>Equity & Drawdown</h2>
    <canvas id="chart" width="800" height="400"></canvas>
    <script>
    fetch('/pnl').then(r => r.json()).then(data => {
        const ctx = document.getElementById('chart').getContext('2d');
        new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.equity.map((_, i) => i),
                datasets: [{
                    label: 'Equity (USDT)',
                    data: data.equity,
                    borderColor: 'green',
                    fill: false
                }, {
                    label: 'Drawdown (%)',
                    data: data.drawdown,
                    borderColor: 'red',
                    fill: false
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    title: { display: true, text: `Total PnL: ${data.total_pnl} USDT | Max DD: ${data.max_dd}% | Sharpe: ${data.sharpe}` }
                }
            }
        });
    });
    </script>
</body>
</html>
"""

@PNL_BP.route("/pnl")
def pnl_json():
    # ✅ Получаем SYMBOLS из config, а не из main
    from config import SYMBOLS
    df = fetch_closed_pnl(os.getenv('BINGX_API_KEY'), os.getenv('BINGX_SECRET_KEY'), use_demo=False, symbols=SYMBOLS)
    stats = calc_stats(df)
    try:
        with open(JSON_FILE, 'w') as f:
            json.dump(stats, f)
    except Exception as e:
        logger.warning(f"Не удалось сохранить PnL: {e}")
    return jsonify(stats)

@PNL_BP.route("/chart")
def chart_html():
    return render_template_string(HTML_PAGE)

def start_pnl_monitor():
    def monitor():
        while True:
            try:
                # ✅ Получаем SYMBOLS из config, а не из main
                from config import SYMBOLS
                df = fetch_closed_pnl(os.getenv('BINGX_API_KEY'), os.getenv('BINGX_SECRET_KEY'), use_demo=False, symbols=SYMBOLS)
                stats = calc_stats(df)
                try:
                    with open(JSON_FILE, 'w') as f:
                        json.dump(stats, f)
                except Exception as e:
                    logger.warning(f"Не удалось сохранить PnL: {e}")

                # пишем итог каждый день в 00:05 UTC
                now = datetime.utcnow()
                if now.hour == 0 and now.minute <= 5:
                    logger.info(f"DAILY-PnL: total={stats['total_pnl']} max_dd={stats['max_dd']}% sharpe={stats['sharpe']}")

                time.sleep(30 * 60)   # 30 минут
            except Exception as e:
                logger.error(f"pnl_monitor: {e}")
                time.sleep(300)

    threading.Thread(target=monitor, daemon=True).start()
    logger.info("PnL-мониторинг запущен (обновление каждые 30 мин)")
