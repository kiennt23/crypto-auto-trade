from binance.enums import *
from binance.websockets import BinanceSocketManager
from binance.client import Client
from app.settings import *
from datetime import datetime
from dateutil import tz
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DCEventType(set):
    def __getattr__(self, name):
        if name in self:
            return name
        raise AttributeError


event_type = DCEventType(['UPTURN', 'DOWNTURN'])
mode = event_type.UPTURN
LAMBDA = 0.004
price_extreme = 0
sing_tz = tz.gettz('UTC+8')


# start aggregated trade websocket for BNBBTC
def process_message(event):
    global mode
    global LAMBDA
    global price_extreme
    price = float(event['k']['c'])
    event_time = datetime.fromtimestamp(event['E']/1000)
    event_time = event_time.replace(tzinfo=sing_tz)
    if mode == event_type.UPTURN:
        if price <= price_extreme * (1 - LAMBDA):
            mode = event_type.DOWNTURN
            price_extreme = price
            logger.info('{} SELL CT or BUY TF {}'.format(event_time, price))
        else:
            price_extreme = max([price_extreme, price])

    else:  # mode is DOWNTURN
        if price >= price_extreme * (1 + LAMBDA):
            mode = event_type.UPTURN
            price_extreme = price
            logger.info('{} BUY CT or SELL TF {}'.format(event_time, price))
        else:
            price_extreme = min([price_extreme, price])


def main():
    logger.info('Starting crypto watch for {}'.format(SYMBOL))
    client = Client(BINANCE_API_KEY, BINANCE_SECRET_KEY)
    bm = BinanceSocketManager(client)
    bm.start_kline_socket(SYMBOL, process_message, interval=KLINE_INTERVAL_1MINUTE)
    bm.start()


if __name__ == '__main__':
    main()
