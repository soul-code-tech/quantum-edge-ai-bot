import os
from dotenv import load_dotenv
load_dotenv()

USE_DEMO   = os.getenv("USE_DEMO", "True").lower() == "true"
LEVERAGE   = int(os.getenv("LEVERAGE", "3"))

RISK_PERCENT      = 1.0
STOP_LOSS_PCT     = 1.5
TAKE_PROFIT_PCT   = 3.0
LSTM_CONFIDENCE   = 0.75

TIMEFRAME = "1h"
SYMBOLS   = ['BTC-USDT', 'ETH-USDT', 'SOL-USDT', 'BNB-USDT', 'XRP-USDT', 'DOGE-USDT', 'ADA-USDT', 'AVAX-USDT']
