from app.settings import *
import logging

logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)


p_ext = INITIAL_P_EXT
mode = INITIAL_MODE


def zi_dct0(delta_p, p_t):
    global mode, p_ext
    if mode == event_type.UPTURN:
        if p_t <= p_ext * (1.0 - delta_p):
            logger.debug('p_ext={} p_t={}'.format(p_ext, p_t))
            mode = event_type.DOWNTURN
            p_ext = p_t
            logger.info('BUY TF mode={} p_t={}'.format(str(mode), p_t))
            return 'BUY TF'
        else:
            p_ext = max([p_ext, p_t])
            logger.debug('p_ext={} p_t={}'.format(p_ext, p_t))
            return 'CONTINUE'

    else:  # mode is DOWNTURN
        if p_t >= p_ext * (1.0 + delta_p):
            logger.debug('p_ext={} p_t={}'.format(p_ext, p_t))
            mode = event_type.UPTURN
            p_ext = p_t
            logger.info('SELL TF mode={} p_t={}'.format(str(mode), p_t))
            return 'SELL TF'

        else:
            p_ext = min([p_ext, p_t])
            logger.debug('p_ext={} p_t={}'.format(p_ext, p_t))
            return 'CONTINUE'