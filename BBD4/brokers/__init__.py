"""
Broker factory — retorna el adapter activo según BROKER en .env.

  BROKER=alpaca  → AlpacaAdapter (paper trading, default)
  BROKER=ibkr    → IBKRAdapter   (IBKR Client Portal Gateway local)
"""
from functools import lru_cache
from brokers.base import BrokerAdapter


@lru_cache(maxsize=1)
def get_broker() -> BrokerAdapter:
    from core.config import settings

    broker = settings.BROKER.lower()

    if broker == "ibkr":
        from brokers.ibkr import IBKRAdapter
        return IBKRAdapter(
            gateway_url=settings.IBKR_GATEWAY_URL,
            account_id=settings.IBKR_ACCOUNT_ID,
        )

    # Default: Alpaca paper
    from brokers.alpaca import AlpacaAdapter
    return AlpacaAdapter(
        api_key=settings.ALPACA_API_KEY,
        api_secret=settings.ALPACA_API_SECRET,
    )
