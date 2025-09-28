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

logger = logging.getLogger("bot")

PNL_BP = Blueprint('pnl', __name__)
JSON_FILE = "pnl_history.json"

def fetch_closed_pnl(api_key, secret, use_demo=False):
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
        income = exchange.fetch_income(since=since, params={'incomeType': 'REALIZED_PNL'})
        df = pd.DataFrame(income)
        if df.empty:
            return pd.DataFrame(columns=['timestamp', 'symbol', 'income', 'balance'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df['income'] = pd.to_numeric(df['income'])
        df = df[['timestamp', 'symbol', 'income']].sort_values('timestamp')
        df['balance'] = df['income'].cumsum()
        return df
    except Exception as e:
        logger.error(f"fetch_closed_pnl: {e}")
        return pd.DataFrame()

def calc_stats(df: pd.DataFrame) -> dict:
    if df.empty:
        return {'equity': [100.0], 'drawdown': [0.0], 'max_dd': 0.0, 'sharpe': 0.0, 'total_pnl': 0.0, 'updated': datetime.utcnow().isoformat()}
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
