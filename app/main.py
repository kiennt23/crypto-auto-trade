import logging
from math import floor

import core.algo
from binance.client import Client
from binance.enums import *
from binance.websockets import BinanceSocketManager
from binance.depthcache import DepthCacheManager
from core.algo import Position

from app.settings import *

logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)


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
quote_asset_balance = client.get_asset_balance(asset=quote_asset)
logger.debug('{} {}'.format(base_asset_balance, quote_asset_balance))

bm = BinanceSocketManager(client)

core.algo.p_ext = 0.0
core.algo.delta_p = LAMBDA
core.algo.config_log(LOG_LEVEL)
core.algo.config_trade_method(TRADE_METHOD)


def process_kline(event):
    global position, best_bid, best_ask
    p_t = float(event['k']['c'])
    timestamp = event['E']
    event_type = core.algo.zi_dct0(p_t)
    if core.algo.is_buy_signaled(event_type, TRADE_METHOD):
        free_quote_balance = float(quote_asset_balance['free'])
        base_by_quote_balance = free_quote_balance / best_ask[0]
        # Only buy half available asset
        half_base_by_quote_balance = base_by_quote_balance * PORTFOLIO_RATIO
        base_qty = round_down(half_base_by_quote_balance, d=base_asset_precision)
        logger.debug('Base qty to BUY {}'.format(base_qty))
        order_response = client.create_order(
            symbol=SYMBOL,
            side=SIDE_BUY,
            type=ORDER_TYPE_LIMIT,
            timeInForce=TIME_IN_FORCE_IOC,
            quantity=base_qty,
            price=best_ask[0])
        # order_response = client.order_limit_buy(symbol=SYMBOL, quantity=base_qty, price=best_ask)
        logger.debug('ORDER {}'.format(order_response))
        position = Position(best_ask[0])
    elif core.algo.is_sell_signaled(event_type, TRADE_METHOD):
        free_base_balance = float(base_asset_balance['free'])
        # free_quote_by_base_balance = free_base_balance * p_t
        # When SELL, close position
        # half_quote_by_base_balance = free_quote_by_base_balance / 2
        half_base_balance = free_base_balance * PORTFOLIO_RATIO
        # quote_qty = round_down(half_quote_by_base_balance, d=quote_asset_precision)
        quote_qty = round_down(half_base_balance, d=base_asset_precision)  # Don't know why
        logger.debug('Quote qty to SELL {}'.format(quote_qty))
        order_response = client.create_order(
            symbol=SYMBOL,
            side=SIDE_SELL,
            type=ORDER_TYPE_LIMIT,
            timeInForce=TIME_IN_FORCE_IOC,
            quantity=quote_qty,
            price=best_bid[0])
        # order_response = client.order_limit_sell(symbol=SYMBOL, quantity=quote_qty, price=best_bid)
        logger.debug('ORDER {}'.format(order_response))
        if position is not None:
            roi = ((best_bid[0] - position.price) / position.price) - (2 * COMMISSION_RATE)
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
        logger.debug('ORDER {} {} {} {} {} {}'.format(event['X'], event['S'], event['s'], event['i'], event['q'], event['p']))


def process_depth(cache):
    global best_bid, best_ask
    if cache is not None:
        best_bid = cache.get_bids()[0]
        best_ask = cache.get_asks()[0]
        logger.debug('Best bid {}, best ask {}'.format(best_bid, best_ask))
    else:
        logger.debug('Depth cache is None')


def main():
    logger.info('Starting crypto watch for {}'.format(SYMBOL))
    bm.start_user_socket(process_user_data)
    bm.start_kline_socket(SYMBOL, process_kline, interval=KLINE_INTERVAL_1MINUTE)
    dcm = DepthCacheManager(client, SYMBOL, callback=process_depth, refresh_interval=60*60)
    bm.start()


if __name__ == '__main__':
    main()
