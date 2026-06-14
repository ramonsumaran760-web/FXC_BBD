"""
Circuit Breaker — patrón de resiliencia para APIs externas.

Estados: closed (normal) → open (fallo) → half-open (prueba)
- Alpaca, Claude, OpenSanctions son los candidatos principales.
"""
from functools import wraps
from typing import Callable, Any
import logging, time

logger = logging.getLogger(__name__)

_OPEN = "open"
_CLOSED = "closed"
_HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(self, name: str, threshold: int = 5, timeout: int = 60):
        self.name = name
        self.threshold = threshold
        self.timeout = timeout

    # ── Claves Redis ─────────────────────────────────────
    def _key_state(self) -> str:
        return f"cb:{self.name}:state"

    def _key_failures(self) -> str:
        return f"cb:{self.name}:failures"

    def _key_last_open(self) -> str:
        return f"cb:{self.name}:last_open"

    # ── Estado ───────────────────────────────────────────
    def get_state(self) -> str:
        try:
            from services.services import cache_get
            state = cache_get(self._key_state())
            if state == _OPEN:
                last_open = cache_get(self._key_last_open()) or 0
                if time.time() - float(last_open) >= self.timeout:
                    self._set_state(_HALF_OPEN)
                    return _HALF_OPEN
            return state or _CLOSED
        except Exception:
            return _CLOSED

    def _set_state(self, state: str):
        try:
            from services.services import cache_set
            cache_set(self._key_state(), state, ttl=self.timeout * 2)
            if state == _OPEN:
                cache_set(self._key_last_open(), str(time.time()), ttl=self.timeout * 2)
        except Exception:
            pass

    def record_failure(self):
        try:
            from services.services import cache_get, cache_set
            failures = int(cache_get(self._key_failures()) or 0) + 1
            cache_set(self._key_failures(), failures, ttl=self.timeout)
            if failures >= self.threshold:
                logger.warning(f"[CircuitBreaker:{self.name}] OPEN — {failures} fallos consecutivos")
                self._set_state(_OPEN)
        except Exception:
            pass

    def record_success(self):
        try:
            from services.services import cache_set
            cache_set(self._key_failures(), 0, ttl=self.timeout)
            self._set_state(_CLOSED)
        except Exception:
            pass

    def is_open(self) -> bool:
        return self.get_state() == _OPEN

    # ── Decorador ────────────────────────────────────────
    def __call__(self, func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            state = self.get_state()
            if state == _OPEN:
                logger.warning(f"[CircuitBreaker:{self.name}] Bloqueado — servicio no disponible")
                raise ServiceUnavailableError(self.name)
            try:
                result = func(*args, **kwargs)
                self.record_success()
                return result
            except ServiceUnavailableError:
                raise
            except Exception as e:
                self.record_failure()
                logger.error(f"[CircuitBreaker:{self.name}] Fallo registrado: {e}")
                raise
        return wrapper


class ServiceUnavailableError(Exception):
    def __init__(self, service_name: str):
        self.service_name = service_name
        super().__init__(f"Servicio {service_name} temporalmente no disponible (Circuit Breaker abierto)")


# ── Instancias globales ───────────────────────────────────
cb_alpaca = CircuitBreaker("alpaca", threshold=5, timeout=60)
cb_claude = CircuitBreaker("claude", threshold=3, timeout=120)
cb_opensanctions = CircuitBreaker("opensanctions", threshold=5, timeout=300)
cb_yfinance = CircuitBreaker("yfinance", threshold=10, timeout=30)
