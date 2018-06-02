import logging
from enum import Enum
import sys


class DCEventType(Enum):
    UPTURN = 1
    DOWNTURN = 2
    OVERSHOOT = 3


class TradeMethod(Enum):
    TF = 1
    CT = 2


class Position:
    def __init__(self, price):
        self.price = price


# p_ext = INITIAL_P_EXT
# mode = INITIAL_MODE

def config_log(log_level):
    global logger
    logging.basicConfig(level=log_level)
    logger = logging.getLogger(__name__)


def config_trade_method(trade_method):
    global mode, p_ext
    if trade_method == TradeMethod.TF:
        mode = DCEventType.UPTURN
        p_ext = 0.0
    else:
        mode = DCEventType.DOWNTURN
        p_ext = 1000000000.0


def zi_dct0(p_t):
    global mode, p_ext, delta_p
    # date = datetime.fromtimestamp(timestamp / 1000, tz=utc)
    # sing_date = date.astimezone(sing_tz)
    if mode == DCEventType.UPTURN:
        if p_t <= p_ext * (1.0 - delta_p):
            logger.debug('p_ext={} p_t={}'.format(p_ext, p_t))
            mode = DCEventType.DOWNTURN
            p_ext = p_t
            # logger.info('At {} BUY TF mode={} p_t={}'.format(sing_date.strftime(fmt), str(mode.name), p_t))
            return mode
        else:
            p_ext = max([p_ext, p_t])
            logger.debug('p_ext={} p_t={}'.format(p_ext, p_t))
            return DCEventType.OVERSHOOT

    else:  # mode is DOWNTURN
        if p_t >= p_ext * (1.0 + delta_p):
            logger.debug('p_ext={} p_t={}'.format(p_ext, p_t))
            mode = DCEventType.UPTURN
            p_ext = p_t
            # logger.info('At {} SELL TF mode={} p_t={}'.format(sing_date.strftime(fmt), str(mode.name), p_t))
            return mode

        else:
            p_ext = min([p_ext, p_t])
            logger.debug('p_ext={} p_t={}'.format(p_ext, p_t))
            return DCEventType.OVERSHOOT


def is_buy_signaled(event_type, trade_method):
    buy_signaled = (trade_method == TradeMethod.TF and DCEventType.DOWNTURN == event_type) or (
            trade_method == TradeMethod.CT and DCEventType.UPTURN == event_type)
    return buy_signaled


def is_sell_signaled(event_type, trade_method):
    sell_signaled = (trade_method == TradeMethod.TF and DCEventType.UPTURN == event_type) or (
            trade_method == TradeMethod.CT and DCEventType.DOWNTURN == event_type)
    return sell_signaled