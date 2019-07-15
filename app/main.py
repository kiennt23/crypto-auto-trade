from datetime import datetime
from decimal import *
from math import floor

import pymongo
import pytz
from binance.client import Client
from binance.depthcache import DepthCacheManager
from binance.enums import *
from binance.websockets import BinanceSocketManager
from core.algo import DCEventType, Config, ZI_DCT0
from pytz import timezone

from app.settings import *

logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)

client = Client(BINANCE_API_KEY, BINANCE_SECRET_KEY)
exchange_info = client.get_exchange_info()
symbol_info = [symbol for symbol in exchange_info['symbols'] if symbol['symbol'] == SYMBOL].pop()
base_asset = symbol_info['baseAsset']
quote_asset = symbol_info['quoteAsset']
quote_asset_precision = symbol_info['quotePrecision']
lot_size_filter = [symbol_filter for symbol_filter in symbol_info['filters'] if
                   'LOT_SIZE' == symbol_filter['filterType']].pop()
minQty = lot_size_filter['minQty'].rstrip('0')
dot_index = minQty.find('.')
if -1 != dot_index:
    minQty = minQty[minQty.find('.') + 1:]

base_asset_precision = len(minQty)

maxQty = lot_size_filter['maxQty']

base_asset_balance = client.get_asset_balance(asset=base_asset)
quote_asset_balance = client.get_asset_balance(asset=quote_asset)
logger.debug('{} {}'.format(base_asset_balance, quote_asset_balance))

bm = BinanceSocketManager(client)

mongo_client = pymongo.MongoClient(MONGO_URL)
state_db = mongo_client['bat-price-state']
strategy = TRADE_METHOD
state_collection = state_db[SYMBOL]
symbol_states = state_collection.find({'S': strategy.name, 'L': str(round(Decimal(LAMBDA), 4))}).sort(
    [('_id', pymongo.DESCENDING)]).limit(1)


class Position:
    def __init__(self, price):
        self.price = price


position = None
best_bid = None
best_ask = None

price_db = mongo_client['bat-price-watcher']


def get_all_records(symbol=SYMBOL, start_time=None):
    symbol_collection = price_db[symbol]
    # start_time = datetime.now()
    if start_time is not None:
        all_records = symbol_collection.find({'_id': {'$gt': start_time}}).sort('_id')
    else:
        all_records = symbol_collection.find().sort('_id')
    return all_records


if symbol_states.count() > 0:
    latest_state = symbol_states[0]
    logger.debug('Latest state {}'.format(latest_state))
    dc_event = DCEventType[latest_state['E']]
    trade_strategy = TradeStrategy[latest_state['S']]
    config = Config(trade_strategy, float(latest_state['L']), dc_event, latest_state['p_ext'])
    start_time = latest_state['t_e']
    all_records = get_all_records(SYMBOL, start_time)
else:
    trade_strategy = TRADE_METHOD
    config = Config(trade_strategy, LAMBDA, DCEventType.DOWNTURN, 0.07)
    all_records = get_all_records(SYMBOL)

dct0_runner = ZI_DCT0(logger, config)

utc = pytz.utc
sing_tz = timezone('Asia/Singapore')
fmt = '%Y-%m-%d %H:%M:%S'
for record in all_records:
    p_t = record['p']
    timestamp = record['_id']
    date = datetime.fromtimestamp(timestamp / 1000, tz=utc)
    end_dc_event = date.astimezone(sing_tz)
    event_type = dct0_runner.observe(p_t, timestamp)
    start_dc_event = datetime.fromtimestamp(dct0_runner.t_start_dc / 1000, tz=utc).astimezone(sing_tz)
    state = {'L': str(round(Decimal(LAMBDA), 4)), 'S': trade_strategy.name, 'E': event_type.name,
             't_s': dct0_runner.t_start_dc, 't_e': timestamp, 'p_ext': dct0_runner.p_start_dc, 'p_t': p_t}
    if dct0_runner.is_buy_signaled():
        logger.debug('DC Event {} start {} end {} BUY {} p_ext={} p_t={}'
                     .format(event_type.name, start_dc_event.strftime(fmt), end_dc_event.strftime(fmt),
                             trade_strategy.name, dct0_runner.p_start_dc, p_t))
        state_collection.update_one({'_id': timestamp}, {'$set': state}, upsert=True)
        position = Position(p_t)
    elif dct0_runner.is_sell_signaled():
        if position is not None:
            roi = ((p_t - position.price) / position.price) - (2 * COMMISSION_RATE)
            logger.debug('DC Event {} start {} end {} SELL {} p_ext={} p_t={}'
                         .format(event_type.name, start_dc_event.strftime(fmt), end_dc_event.strftime(fmt),
                                 trade_strategy.name, dct0_runner.p_start_dc, p_t))
            state_collection.update_one({'_id': timestamp}, {'$set': state}, upsert=True)
            position = None  # After sell, clear the position


def process_kline(event):
    global position, best_bid, best_ask
    p_t: float = float(event['k']['c'])
    observe = dct0_runner.observe(p_t)
    if dct0_runner.is_buy_signaled():
        free_quote_balance = float(quote_asset_balance['free'])
        price_to_buy = p_t if p_t <= best_ask[0] else best_ask[0]
        base_by_quote_balance = free_quote_balance / price_to_buy
        qty_to_buy = base_by_quote_balance * BUY_RATIO
        base_qty = round_down(qty_to_buy, d=base_asset_precision)
        logger.debug('Base qty to BUY {}'.format(base_qty))
        order_response = client.create_order(
            symbol=SYMBOL,
            side=SIDE_BUY,
            type=ORDER_TYPE_LIMIT,
            timeInForce=TIME_IN_FORCE_GTC,
            quantity=base_qty,
            price=price_to_buy)
        logger.debug('ORDER {}'.format(order_response))
        position = Position(price_to_buy)
    elif dct0_runner.is_sell_signaled():
        free_base_balance = float(base_asset_balance['free'])
        qty_to_sell = free_base_balance * SELL_RATIO
        quote_qty = round_down(qty_to_sell, d=base_asset_precision)
        logger.debug('Quote qty to SELL {}'.format(quote_qty))
        price_to_sell = p_t if p_t >= best_bid[0] else best_bid[0]
        order_response = client.create_order(
            symbol=SYMBOL,
            side=SIDE_SELL,
            type=ORDER_TYPE_LIMIT,
            timeInForce=TIME_IN_FORCE_GTC,
            quantity=quote_qty,
            price=price_to_sell)
        logger.debug('ORDER {}'.format(order_response))
        if position is not None:
            roi = ((price_to_sell - position.price) / position.price) - (2 * COMMISSION_RATE)
            logger.info('Estimated ROI {}'.format(str(roi)))
            position = None


def round_down(n, d=8):
    d = int('1' + ('0' * d))
    return floor(n * d) / d


def process_user_data(event):
    if 'outboundAccountInfo' == event['e']:
        base_asset_event = [asset for asset in event['B'] if asset['a'] == base_asset].pop()
        base_asset_balance['free'] = base_asset_event['f']
        base_asset_balance['locked'] = base_asset_event['l']
        quote_asset_event = [asset for asset in event['B'] if asset['a'] == quote_asset].pop()
        quote_asset_balance['free'] = quote_asset_event['f']
        quote_asset_balance['locked'] = quote_asset_event['l']
        logger.debug('{} {}'.format(base_asset_balance, quote_asset_balance))
    if 'executionReport' == event['e']:
        logger.debug(
            'ORDER {} {} {} {} {} {}'.format(event['X'], event['S'], event['s'], event['i'], event['q'], event['p']))


def process_depth(cache):
    global best_bid, best_ask
    if cache is not None:
        best_bid = cache.get_bids()[0]
        best_ask = cache.get_asks()[0]
    else:
        logger.debug('Depth cache is None')


def main():
    logger.info('Starting crypto watch for {}'.format(SYMBOL))
    bm.start_user_socket(process_user_data)
    bm.start_kline_socket(SYMBOL, process_kline, interval=KLINE_INTERVAL_1MINUTE)
    dcm = DepthCacheManager(client, SYMBOL, callback=process_depth, refresh_interval=60)
    bm.start()


if __name__ == '__main__':
    main()
