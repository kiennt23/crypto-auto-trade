from binance.enums import *
from binance.websockets import BinanceSocketManager
from binance.client import Client

from app.settings import *
import logging
from decimal import *


logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)


class Position:
    def __init__(self, price):
        self.price = price


p_ext = INITIAL_P_EXT
mode = INITIAL_MODE

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


def process_kline(event):
    global mode
    global LAMBDA
    global p_ext
    global position
    p_t = float(event['k']['c'])
    zi_dct0(LAMBDA, p_t)


def zi_dct0(delta_p, p_t):
    global mode, p_ext, position
    if mode == event_type.UPTURN:
        if p_t <= p_ext * (1.0 - delta_p):
            logger.debug('p_ext={} p_t={}'.format(p_ext, p_t))
            mode = event_type.DOWNTURN
            p_ext = p_t
            logger.info('BUY TF mode={} p_t={}'.format(str(mode), p_t))
            free_quote_balance = float(quote_asset_balance['free'])
            base_by_quote_balance = free_quote_balance / p_t
            getcontext().prec = base_asset_precision
            getcontext().rounding = ROUND_DOWN
            # Only buy half available asset
            half_base_by_quote_balance = base_by_quote_balance / 2
            base_qty = str(round(Decimal(half_base_by_quote_balance), base_asset_precision))
            logger.debug('Base qty to BUY {}'.format(base_qty))
            order_response = client.order_limit_buy(symbol=SYMBOL, quantity=base_qty, price=p_t)
            logger.debug('ORDER {}'.format(order_response))
            position = Position(p_t)
        else:
            p_ext = max([p_ext, p_t])
            logger.debug('p_ext={} p_t={}'.format(p_ext, p_t))

    else:  # mode is DOWNTURN
        if p_t >= p_ext * (1.0 + delta_p):
            logger.debug('p_ext={} p_t={}'.format(p_ext, p_t))
            mode = event_type.UPTURN
            p_ext = p_t
            logger.info('SELL TF mode={} p_t={}'.format(str(mode), p_t))
            free_base_balance = float(base_asset_balance['free'])
            free_quote_by_base_balance = free_base_balance * p_t
            # When SELL, close position
            getcontext().prec = quote_asset_precision
            getcontext().rounding = ROUND_DOWN
            half_quote_by_base_balance = free_quote_by_base_balance / 2
            quote_qty = str(round(Decimal(half_quote_by_base_balance), quote_asset_precision))
            logger.debug('Quote qty to SELL {}'.format(quote_qty))
            order_response = client.order_limit_sell(symbol=SYMBOL, quantity=quote_qty, price=p_t)
            logger.debug('ORDER {}'.format(order_response))
            if position is not None:
                roi = ((p_t - position.price) / position.price) - (2 * COMMISSION_RATE)
                logger.info('Estimated ROI {}'.format(str(roi)))
                position = None

        else:
            p_ext = min([p_ext, p_t])
            logger.debug('p_ext={} p_t={}'.format(p_ext, p_t))


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
    if cache is not None:
        best_bid = cache.get_bids()[:1]
        best_ask = cache.get_asks()[:1]
        logger.debug('Best bid {}, best ask {}'.format(best_bid, best_ask))
    else:
        logger.debug('Depth cache is None')


def main():
    logger.info('Starting crypto watch for {}'.format(SYMBOL))
    bm.start_user_socket(process_user_data)
    bm.start_kline_socket(SYMBOL, process_kline, interval=KLINE_INTERVAL_1MINUTE)
    bm.start()


if __name__ == '__main__':
    main()
