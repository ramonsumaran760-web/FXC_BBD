"""
BrokerAdapter — interfaz común para todos los brokers.
Implementaciones: AlpacaAdapter, IBKRAdapter.
"""
from abc import ABC, abstractmethod


class BrokerAdapter(ABC):

    @property
    @abstractmethod
    def name(self) -> str:
        """Identificador del broker (ej: 'alpaca_paper', 'ibkr_live')."""
        ...

    @abstractmethod
    def get_account(self) -> dict:
        """
        Retorna estado de cuenta normalizado:
        {equity, cash, buying_power, portfolio_value, status, source}
        """
        ...

    @abstractmethod
    def place_order(self, ticker: str, monto_usd: float, side: str = "buy",
                    order_type: str = "market", limit_price: float = None) -> dict:
        """
        Ejecuta una orden en el broker.
        Retorna respuesta normalizada:
        {id, symbol, side, type, filled_qty, filled_avg_price,
         filled_notional, status, broker, submitted_at, filled_at}
        En error retorna: {error: str}
        """
        ...

    @abstractmethod
    def get_positions(self) -> list:
        """
        Retorna lista de posiciones normalizadas:
        [{symbol, qty, avg_entry_price, current_price,
          market_value, unrealized_pl, unrealized_plpc}]
        """
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> dict:
        """Cancela una orden pendiente. Retorna {status: 'cancelled'} o {error: str}."""
        ...
