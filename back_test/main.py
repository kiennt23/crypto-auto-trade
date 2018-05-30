import logging
from back_test.settings import *


logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)


def main():
    logger.info('Starting crypto back test for {}'.format(SYMBOL))


if __name__ == '__main__':
    main()