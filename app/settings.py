import logging
import os

from core.algo import TradeStrategy

BINANCE_API_KEY = os.environ['BINANCE_API_KEY']
BINANCE_SECRET_KEY = os.environ['BINANCE_SECRET_KEY']
MONGO_URL = os.environ['MONGO_URL']

LOG_LEVEL = logging.INFO

SYMBOL = 'ETHBTC'
LAMBDA = 0.0101
COMMISSION_RATE = 0.0005
TRADE_METHOD = TradeStrategy.CT
BUY_RATIO = 1
SELL_RATIO = 1
THRESHOLD_WITHOUT_SIGNAL = 0.02
