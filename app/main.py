from binance.enums import *
from binance.websockets import BinanceSocketManager
from binance.client import Client
from pymongo.errors import DuplicateKeyError

from app.settings import *
# from datetime import datetime
from dateutil import tz
import logging
import pymongo
from decimal import *


logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)


class Position:
    def __init__(self, order_id, qty, price):
        self.order_id = order_id
        self.qty = qty
        self.price = price
        self.status = 'OPEN'


p_ext = INITIAL_P_EXT
mode = INITIAL_MODE
sing_tz = tz.gettz('UTC+8')
mongo_client = pymongo.MongoClient("mongodb+srv://bat-price-watcher:QRTHQ3MfX5ia0oMh@cluster0-w2mrr.mongodb.net/bat-price-watcher?retryWrites=true")
db = mongo_client['bat-price-watcher']

client = Client(BINANCE_API_KEY, BINANCE_SECRET_KEY)
exchange_info = client.get_exchange_info()
symbol_info = [symbol for symbol in exchange_info['symbols'] if symbol['symbol'] == SYMBOL].pop()
base_asset = symbol_info['baseAsset']
quote_asset = symbol_info['quoteAsset']
quote_asset_precision = symbol_info['quotePrecision']
lot_size_filter = [symbol_filter for symbol_filter in symbol_info['filters'] if 'LOT_SIZE' == symbol_filter['filterType']].pop()
minQty = lot_size_filter['minQty'].rstrip('0')
dot_index = minQty.find('.')
if -1 != dot_index:
    minQty = minQty[minQty.find('.') + 1:]

base_asset_precision = len(minQty)

maxQty = lot_size_filter['maxQty']

base_asset_balance = client.get_asset_balance(asset=base_asset)
logger.debug(base_asset_balance)
quote_asset_balance = client.get_asset_balance(asset=quote_asset)
logger.debug(quote_asset_balance)

bm = BinanceSocketManager(client)


def process_kline(event):
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
        logger.error('Duplicate event {}'.format(price_doc['_id']))
    if mode == event_type.UPTURN:
        if p_t <= p_ext * (1.0 - LAMBDA):
            logger.debug('p_ext={} p_t={}'.format(p_ext, p_t))
            mode = event_type.DOWNTURN
            p_ext = p_t
            buy(mode, p_t)
        else:
            p_ext = max([p_ext, p_t])
            logger.debug('p_ext={} p_t={}'.format(p_ext, p_t))

    else:  # mode is DOWNTURN
        if p_t >= p_ext * (1.0 + LAMBDA):
            logger.debug('p_ext={} p_t={}'.format(p_ext, p_t))
            mode = event_type.UPTURN
            p_ext = p_t
            sell(mode, p_t, position)
        else:
            p_ext = min([p_ext, p_t])
            logger.debug('p_ext={} p_t={}'.format(p_ext, p_t))


def sell(mode, p_t, position):
    logger.info('SELL TF mode={} p_t={}'.format(str(mode), p_t))
    # When SELL, close position
    if position is not None and 'FILLED' == position.status:
        getcontext().prec = quote_asset_precision
        getcontext().rounding = ROUND_DOWN
        quote_qty = str(round(Decimal(position.qty), quote_asset_precision))
        order_response = client.order_limit_sell(symbol=SYMBOL, quantity=quote_qty, price=p_t)
        logger.debug('ORDER {}'.format(order_response))
        roi = ((p_t - position.price) / position.price) - (2 * COMMISSION_RATE)
        if ORDER_STATUS_FILLED == order_response['status']:
            logger.info('ROI {}'.format(str(roi)))
        else:
            logger.info('Estimated ROI {}'.format(str(roi)))


def buy(mode, p_t):
    global position
    logger.info('BUY TF mode={} p_t={}'.format(str(mode), p_t))
    free_quote_balance = float(quote_asset_balance['free'])
    base_by_quote_balance = free_quote_balance / p_t
    getcontext().prec = base_asset_precision
    getcontext().rounding = ROUND_DOWN
    base_qty = str(round(Decimal(base_by_quote_balance), base_asset_precision))
    logger.debug('BASE QTY {}'.format(base_qty))
    order_response = client.order_limit_buy(symbol=SYMBOL, quantity=base_qty, price=p_t)
    logger.debug('ORDER {}'.format(order_response))
    # When BUY, create a new Position
    if ORDER_STATUS_FILLED == order_response['status']:
        qty = float(order_response['executedQty'])
        position = Position(order_response['orderId'], qty, p_t)
        position.status = 'FILLED'
    else:
        position = Position(order_response['orderId'], 0.0, p_t)


def process_user_data(event):
    if 'outboundAccountInfo' == event['e']:
        base_asset_event = [asset for asset in event['B'] if asset['a'] == base_asset].pop()
        base_asset_balance['free'] = base_asset_event['f']
        base_asset_balance['locked'] = base_asset_event['l']
        logger.debug(base_asset_balance)
        quote_asset_event = [asset for asset in event['B'] if asset['a'] == quote_asset].pop()
        quote_asset_balance['free'] = quote_asset_event['f']
        quote_asset_balance['locked'] = quote_asset_event['l']
        logger.debug(quote_asset_balance)
    if 'executionReport' == event['e']:
        order_id = event['i']
        order_status = event['X']
        if order_id == position.order_id and 'OPEN' == position.status and ORDER_STATUS_FILLED == order_status:
            position.qty += float(event['l'])
            position.status = 'FILLED'


def main():
    logger.info('Starting crypto watch for {}'.format(SYMBOL))
    bm.start_kline_socket(SYMBOL, process_kline, interval=KLINE_INTERVAL_1MINUTE)
    bm.start_user_socket(process_user_data)
    bm.start()


if __name__ == '__main__':
    main()
