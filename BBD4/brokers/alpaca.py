"""
AlpacaAdapter — implementación de BrokerAdapter para Alpaca Paper Trading.
Migrado desde services/services.py (funciones alpaca_*).
"""
import hashlib, logging, time
from datetime import datetime, timezone
import requests

from brokers.base import BrokerAdapter

logger = logging.getLogger(__name__)

ALPACA_BASE = "https://paper-api.alpaca.markets/v2"


def _headers(key: str, secret: str) -> dict:
    return {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret,
            "Content-Type": "application/json"}


def _is_demo(key: str) -> bool:
    return not key or key in ("DEMO_KEY", "demo", "")


class AlpacaAdapter(BrokerAdapter):

    def __init__(self, api_key: str, api_secret: str):
        self._key = api_key
        self._secret = api_secret

    @property
    def name(self) -> str:
        return "alpaca_demo" if _is_demo(self._key) else "alpaca_paper"

    def get_account(self) -> dict:
        if _is_demo(self._key):
            return {"equity": "12847.32", "cash": "3421.10",
                    "buying_power": "6842.20", "portfolio_value": "12847.32",
                    "status": "ACTIVE", "daytrade_count": 0, "source": "demo"}
        from core.circuit_breaker import cb_alpaca
        try:
            @cb_alpaca
            def _req():
                r = requests.get(f"{ALPACA_BASE}/account",
                                 headers=_headers(self._key, self._secret), timeout=8)
                return r.json() if r.ok else {"error": r.text}
            return _req()
        except Exception as e:
            return {"error": str(e)}

    def place_order(self, ticker: str, monto_usd: float, side: str = "buy",
                    order_type: str = "market", limit_price: float = None) -> dict:
        from services.services import get_market_prices
        prices = get_market_prices([ticker])
        price = prices.get(ticker, {}).get("price", 100)
        fracciones = round(monto_usd / price, 8) if price > 0 else 0

        if _is_demo(self._key):
            return {
                "id": f"ord_{hashlib.md5(f'{ticker}{time.time()}'.encode()).hexdigest()[:12]}",
                "symbol": ticker, "side": side, "type": order_type,
                "notional": str(monto_usd), "filled_notional": str(monto_usd),
                "filled_qty": str(fracciones), "filled_avg_price": str(round(price, 4)),
                "status": "filled", "broker": self.name,
                "submitted_at": datetime.now(timezone.utc).isoformat(),
                "filled_at": datetime.now(timezone.utc).isoformat(),
            }

        from core.circuit_breaker import cb_alpaca
        try:
            @cb_alpaca
            def _req():
                payload = {"symbol": ticker, "side": side, "type": order_type,
                           "time_in_force": "day" if order_type == "market" else "gtc",
                           "notional": str(round(monto_usd, 2))}
                if order_type == "limit" and limit_price:
                    payload["limit_price"] = str(limit_price)
                r = requests.post(f"{ALPACA_BASE}/orders",
                                  headers=_headers(self._key, self._secret),
                                  json=payload, timeout=12)
                return r.json() if r.ok else {"error": r.text}
            return _req()
        except Exception as e:
            return {"error": str(e)}

    def get_positions(self) -> list:
        if _is_demo(self._key):
            return [
                {"symbol": "AAPL", "qty": "2.3456", "avg_entry_price": "189.50",
                 "current_price": "195.20", "market_value": "457.89",
                 "unrealized_pl": "13.38", "unrealized_plpc": "0.030"},
                {"symbol": "NVDA", "qty": "0.8721", "avg_entry_price": "850.00",
                 "current_price": "912.40", "market_value": "795.27",
                 "unrealized_pl": "54.40", "unrealized_plpc": "0.073"},
            ]
        from core.circuit_breaker import cb_alpaca
        try:
            @cb_alpaca
            def _req():
                r = requests.get(f"{ALPACA_BASE}/positions",
                                 headers=_headers(self._key, self._secret), timeout=8)
                return r.json() if r.ok else []
            return _req()
        except Exception:
            return []

    def cancel_order(self, order_id: str) -> dict:
        if _is_demo(self._key):
            return {"status": "cancelled", "id": order_id}
        from core.circuit_breaker import cb_alpaca
        try:
            @cb_alpaca
            def _req():
                r = requests.delete(f"{ALPACA_BASE}/orders/{order_id}",
                                    headers=_headers(self._key, self._secret), timeout=8)
                return {"status": "cancelled"} if r.status_code == 204 else {"error": r.text}
            return _req()
        except Exception as e:
            return {"error": str(e)}
