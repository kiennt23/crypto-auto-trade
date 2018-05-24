from binance.enums import *
from binance.websockets import BinanceSocketManager
from binance.client import Client
from pymongo.errors import DuplicateKeyError

from app.settings import *
# from datetime import datetime
from dateutil import tz
import logging
import pymongo


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DCEventType(set):
    def __getattr__(self, name):
        if name in self:
            return name
        raise AttributeError


class Position:
    def __init__(self, qty, price):
        self.qty = qty
        self.price = price
        self.status = 'OPEN'


event_type = DCEventType(['UPTURN', 'DOWNTURN'])
mode = event_type.DOWNTURN
LAMBDA = 0.004
p_ext = 0.0
sing_tz = tz.gettz('UTC+8')
client = pymongo.MongoClient("mongodb+srv://bat-price-watcher:QRTHQ3MfX5ia0oMh@cluster0-w2mrr.mongodb.net/bat-price-watcher?retryWrites=true")
db = client['bat-price-watcher']


def process_message(event):
    global mode
    global LAMBDA
    global p_ext
    global position
    p_t = float(event['k']['c'])
    # event_time = datetime.fromtimestamp(event['E']/1000)
    # event_time = event_time.replace(tzinfo=sing_tz)
    price_doc = {'_id': event['E'], 'p': p_t}
    try:
        symbol_collection = db[SYMBOL]
        symbol_collection.insert_one(price_doc)
    except DuplicateKeyError:
        logger.error('Duplicate event {}'.format(event['_id']))
    if mode == event_type.UPTURN:
        if p_t <= p_ext * (1.0 - LAMBDA):
            logger.info('p_ext={} p_t={}'.format(p_ext, p_t))
            mode = event_type.DOWNTURN
            p_ext = p_t
            logger.info('SELL CT mode={} p_t={}'.format(str(mode), p_t))
            # When SELL, close position
            if position is not None:
                roi = (position.price - p_t) / position.price
                logger.info('ROI {}'.format(str(roi)))
        else:
            p_ext = max([p_ext, p_t])
            logger.info('p_ext={} p_t={}'.format(p_ext, p_t))

    else:  # mode is DOWNTURN
        if p_t >= p_ext * (1.0 + LAMBDA):
            logger.info('p_ext={} p_t={}'.format(p_ext, p_t))
            mode = event_type.UPTURN
            p_ext = p_t
            logger.info('BUY CT mode={} p_t={}'.format(str(mode), p_t))
            # When BUY, create a new Position
            position = Position(1.0, p_t)
        else:
            p_ext = min([p_ext, p_t])
            logger.info('p_ext={} p_t={}'.format(p_ext, p_t))


def main():
    logger.info('Starting crypto watch for {}'.format(SYMBOL))
    client = Client(BINANCE_API_KEY, BINANCE_SECRET_KEY)
    exchange_info = client.get_exchange_info()
    symbol_info = [symbol for symbol in exchange_info['symbols'] if symbol['symbol'] == 'BNBBTC'].pop()

    bm = BinanceSocketManager(client)
    bm.start_kline_socket(SYMBOL, process_message, interval=KLINE_INTERVAL_1MINUTE)
    bm.start()


if __name__ == '__main__':
    main()
