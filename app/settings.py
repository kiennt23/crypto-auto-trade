import logging

BINANCE_API_KEY = 'FbtgTH5TAgpggxR4ltDMMjQaCLpVG2AHmzNbtwUYKiInUdbqdVnO79AXHAKnsw5X'
BINANCE_SECRET_KEY = 'g78DnJ3VMB4TZPt3rVppf5lPKqWj9Ei0EMZjyw4IktoAmv5LsBqmVvWZsxhFZbRZ'

LOG_LEVEL = logging.DEBUG

SYMBOL = 'BNBBTC'
LAMBDA = 0.004
INITIAL_P_EXT = 0.0
COMMISSION_RATE = 0.0005


class DCEventType(set):
    def __getattr__(self, name):
        if name in self:
            return name
        raise AttributeError


event_type = DCEventType(['UPTURN', 'DOWNTURN'])
mode = event_type.UPTURN

