"""
IBKRAdapter — Interactive Brokers Client Portal Web API.

Requisitos:
  1. Tener cuenta IBKR (interactivebrokers.com)
  2. Descargar el Client Portal Gateway:
     https://www.interactivebrokers.com/en/trading/ib-api.php
  3. Ejecutar: java -jar root/run.jar root/conf.yaml
  4. Autenticarse en: https://localhost:5000 (solo la primera vez)
  5. El gateway queda en: https://localhost:5000/v1/api/

Variables de entorno requeridas:
  IBKR_GATEWAY_URL=https://localhost:5000
  IBKR_ACCOUNT_ID=U1234567   (ver en la app de IBKR o /iserver/accounts)
"""
import logging, time
from datetime import datetime, timezone
import requests

from brokers.base import BrokerAdapter

logger = logging.getLogger(__name__)

# Cache local de conids (ticker → contract ID de IBKR)
_conid_cache: dict[str, int] = {}


class IBKRAdapter(BrokerAdapter):

    def __init__(self, gateway_url: str, account_id: str):
        # IBKR gateway usa certificado auto-firmado — desactivar verify en dev local
        self._base = gateway_url.rstrip("/") + "/v1/api"
        self._account = account_id
        self._session = requests.Session()
        self._session.verify = False  # gateway local con cert auto-firmado

    @property
    def name(self) -> str:
        return "ibkr_live"

    # ── Helpers internos ──────────────────────────────────

    def _get(self, path: str, **kwargs) -> requests.Response:
        return self._session.get(f"{self._base}{path}", timeout=10, **kwargs)

    def _post(self, path: str, **kwargs) -> requests.Response:
        return self._session.post(f"{self._base}{path}", timeout=15, **kwargs)

    def _delete(self, path: str, **kwargs) -> requests.Response:
        return self._session.delete(f"{self._base}{path}", timeout=10, **kwargs)

    def _tickle(self):
        """Mantiene la sesión activa. Llamar periódicamente."""
        try:
            self._post("/tickle")
        except Exception:
            pass

    def _resolve_conid(self, ticker: str) -> int | None:
        """Resuelve ticker a contract ID de IBKR (con cache local)."""
        if ticker in _conid_cache:
            return _conid_cache[ticker]
        try:
            from core.circuit_breaker import cb_ibkr
            @cb_ibkr
            def _req():
                r = self._get("/iserver/secdef/search", params={"symbol": ticker})
                if r.ok:
                    results = r.json()
                    for item in results:
                        if (item.get("ticker", "").upper() == ticker.upper()
                                and item.get("secType") == "STK"):
                            return item.get("conid")
                return None
            conid = _req()
            if conid:
                _conid_cache[ticker] = conid
            return conid
        except Exception as e:
            logger.warning(f"IBKR conid lookup {ticker}: {e}")
            return None

    def _confirm_order(self, reply_id: str) -> dict:
        """Confirma una orden que requiere aprobación adicional de IBKR."""
        try:
            r = self._post(f"/iserver/reply/{reply_id}", json={"confirmed": True})
            if r.ok:
                data = r.json()
                if isinstance(data, list) and data:
                    return data[0]
            return {"error": "confirm failed"}
        except Exception as e:
            return {"error": str(e)}

    # ── Interfaz pública ──────────────────────────────────

    def get_account(self) -> dict:
        from core.circuit_breaker import cb_ibkr
        try:
            @cb_ibkr
            def _req():
                r = self._get(f"/portfolio/{self._account}/summary")
                if not r.ok:
                    return {"error": r.text}
                data = r.json()
                # Normalizar al formato común
                return {
                    "equity":          str(data.get("netliquidation", {}).get("amount", 0)),
                    "cash":            str(data.get("cashbalance", {}).get("amount", 0)),
                    "buying_power":    str(data.get("buyingpower", {}).get("amount", 0)),
                    "portfolio_value": str(data.get("netliquidation", {}).get("amount", 0)),
                    "status":          "ACTIVE",
                    "source":          "ibkr_live",
                }
            return _req()
        except Exception as e:
            return {"error": str(e)}

    def place_order(self, ticker: str, monto_usd: float, side: str = "buy",
                    order_type: str = "market", limit_price: float = None) -> dict:
        from core.circuit_breaker import cb_ibkr
        from services.services import get_market_prices

        conid = self._resolve_conid(ticker)
        if not conid:
            return {"error": f"No se encontró contrato IBKR para {ticker}"}

        # Calcular cantidad desde precio actual
        prices = get_market_prices([ticker])
        price = prices.get(ticker, {}).get("price", 0)
        if price <= 0:
            return {"error": f"Sin precio para {ticker}"}
        qty = round(monto_usd / price, 4)

        payload = {
            "acctId":    self._account,
            "conid":     conid,
            "secType":   f"{conid}:STK",
            "orderType": "MKT" if order_type == "market" else "LMT",
            "side":      side.upper(),
            "quantity":  qty,
            "tif":       "DAY",
        }
        if order_type == "limit" and limit_price:
            payload["price"] = limit_price

        try:
            @cb_ibkr
            def _req():
                r = self._post(
                    f"/iserver/account/{self._account}/orders",
                    json={"orders": [payload]}
                )
                if not r.ok:
                    return {"error": r.text}
                data = r.json()
                if isinstance(data, list) and data:
                    item = data[0]
                    # IBKR puede pedir confirmación adicional
                    if "id" in item:
                        confirmed = self._confirm_order(item["id"])
                        if "order_id" in confirmed:
                            item = confirmed
                    order_id = str(item.get("order_id", item.get("id", "")))
                    return {
                        "id":               order_id,
                        "symbol":           ticker,
                        "side":             side,
                        "type":             order_type,
                        "filled_qty":       str(qty),
                        "filled_avg_price": str(round(price, 4)),
                        "filled_notional":  str(round(monto_usd, 2)),
                        "status":           "filled",
                        "broker":           self.name,
                        "submitted_at":     datetime.now(timezone.utc).isoformat(),
                        "filled_at":        datetime.now(timezone.utc).isoformat(),
                    }
                return {"error": "Respuesta inesperada de IBKR"}
            return _req()
        except Exception as e:
            return {"error": str(e)}

    def get_positions(self) -> list:
        from core.circuit_breaker import cb_ibkr
        try:
            @cb_ibkr
            def _req():
                r = self._get(f"/portfolio/{self._account}/positions/0")
                if not r.ok:
                    return []
                raw = r.json()
                positions = []
                for p in raw:
                    qty = p.get("position", 0)
                    if qty == 0:
                        continue
                    avg = p.get("avgCost", 0)
                    mkt = p.get("mktPrice", 0)
                    val = p.get("mktValue", 0)
                    pnl = p.get("unrealizedPnl", 0)
                    pnl_pct = round(pnl / max(abs(avg * qty), 1), 6)
                    positions.append({
                        "symbol":          p.get("contractDesc", "").split()[0],
                        "qty":             str(qty),
                        "avg_entry_price": str(round(avg, 4)),
                        "current_price":   str(round(mkt, 4)),
                        "market_value":    str(round(val, 2)),
                        "unrealized_pl":   str(round(pnl, 2)),
                        "unrealized_plpc": str(round(pnl_pct, 6)),
                    })
                return positions
            return _req()
        except Exception:
            return []

    def cancel_order(self, order_id: str) -> dict:
        from core.circuit_breaker import cb_ibkr
        try:
            @cb_ibkr
            def _req():
                r = self._delete(f"/iserver/account/{self._account}/order/{order_id}")
                if r.status_code in (200, 204):
                    return {"status": "cancelled", "id": order_id}
                return {"error": r.text}
            return _req()
        except Exception as e:
            return {"error": str(e)}
