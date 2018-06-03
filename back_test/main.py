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


def dct1():
    global position
    logger.info('Starting crypto back test for {}'.format(SYMBOL))

    start = 0.001
    stop = 0.05
    step = 0.001
    lambdas = np.arange(start, stop, step)
    max_roi_method, max_roi_lambda, max_roi = calculate_max_lambda(lambdas)
    start = max_roi_lambda - 2*step
    stop = max_roi_lambda + 2*step
    step = step / 10
    lambdas = np.arange(start, stop, step)
    max_roi_method, max_roi_lambda, max_roi = calculate_max_lambda(lambdas)
    logger.info('FINAL MAX {} LAMBDA {} ROI {}%'.format(max_roi_method.name, str(round(Decimal(max_roi_lambda), 4)),
                                                  str(round(Decimal(max_roi * 100), 3))))


def calculate_max_lambda(lambdas):
    global position
    symbol_collection = db[SYMBOL]
    start_time = datetime.now()
    all_records = list(symbol_collection.find().sort('_id'))
    end_time = datetime.now()
    logger.info('Prices query time {}'.format(str(end_time - start_time)))
    first_record_date = datetime.fromtimestamp(all_records[0]['_id'] / 1000, tz=utc).astimezone(sing_tz)
    last_record_date = datetime.fromtimestamp(all_records[-1]['_id'] / 1000, tz=utc).astimezone(sing_tz)
    logger.info('Evaluation time from {} to {}'.format(first_record_date.strftime(fmt), last_record_date.strftime(fmt)))
    getcontext().prec = 5
    max_roi = None
    max_roi_method = None
    max_roi_lambda = None
    for trade_method in TradeMethod:
        for LAMBDA in lambdas:
            core.algo.config_trade_method(trade_method)
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
            np_result = np.array(result)
            np_result += 1
            sum_roi = np.prod(np_result) - 1
            if sum_roi > 0:
                logger.info('{} LAMBDA {} ROI {}%'.format(trade_method.name, str(round(Decimal(LAMBDA), 3)),
                                                          str(round(Decimal(sum_roi * 100), 2))))
            if max_roi is None or max_roi < sum_roi:
                max_roi = sum_roi
                max_roi_method = trade_method
                max_roi_lambda = LAMBDA
    logger.info('MAX {} LAMBDA {} ROI {}%'.format(max_roi_method.name, str(round(Decimal(max_roi_lambda), 4)),
                                                  str(round(Decimal(max_roi * 100), 3))))
    return max_roi_method, max_roi_lambda, max_roi


if __name__ == '__main__':
    dct1()