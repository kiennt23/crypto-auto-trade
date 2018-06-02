from back_test.settings import *
from core.algo import Position, TradeMethod
import core.algo

import pymongo
from datetime import datetime
from pytz import timezone
import pytz
import numpy as np
from decimal import *

utc = pytz.utc
sing_tz = timezone('Asia/Singapore')
fmt = '%Y-%m-%d %H:%M:%S'

logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)

mongo_client = pymongo.MongoClient(MONGO_URL)
db = mongo_client['bat-price-watcher']

core.algo.config_log(LOG_LEVEL)


def main():
    global position
    logger.info('Starting crypto back test for {}'.format(SYMBOL))

    symbol_collection = db[SYMBOL]
    start_time = datetime.now()
    all_records = list(symbol_collection.find().sort('_id'))
    end_time = datetime.now()
    logger.info('Prices query time {}'.format(str(end_time - start_time)))
    lambdas = np.arange(0.001, 0.05, 0.001)
    getcontext().prec = 3
    for trade_method in TradeMethod:
        core.algo.config_trade_method(trade_method)
        for LAMBDA in lambdas:
            core.algo.delta_p = LAMBDA
            result = []
            for record in all_records:
                p_t = record['p']
                timestamp = record['_id']
                date = datetime.fromtimestamp(timestamp / 1000, tz=utc)
                sing_date = date.astimezone(sing_tz)
                event_type = core.algo.zi_dct0(p_t)
                if core.algo.is_buy_signaled(event_type, trade_method):
                    logger.debug('At {} BUY {} mode={} p_t={}'.format(sing_date.strftime(fmt), trade_method.name,
                                                                      event_type.name, p_t))
                    position = Position(p_t)
                elif core.algo.is_sell_signaled(event_type, trade_method):
                    if position is not None:
                        roi = ((p_t - position.price) / position.price) - (2 * COMMISSION_RATE)
                        logger.debug('At {} SELL {} mode={} p_t={}'.format(sing_date.strftime(fmt), trade_method.name,
                                                                           event_type.name, p_t))
                        logger.debug('Estimated ROI {}'.format(str(roi)))
                        result.append(roi)
                        position = None

            sum_roi = sum(result)
            if sum_roi > 0:
                logger.info('Total ROI {} {} {}'.format(str(round(Decimal(LAMBDA), 3)), trade_method.name, str(sum_roi)))


if __name__ == '__main__':
    main()