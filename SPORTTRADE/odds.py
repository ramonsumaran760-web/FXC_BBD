"""
odds.py — Módulo de gestión de cuotas FXC_BBD.

Responsabilidades:
  • Calcular probabilidades implícitas con Overround Correction
  • Calcular EV = (Probabilidad_IA × Cuota_Casa) − 1
  • Clasificar señal: ALTO | MEDIO | BAJO | SIN_VALOR
  • Detectar anomalías de cuota (circuit breaker input)
  • Capturar cuotas back y lay separadas — Brecha B
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import time


# ─── UMBRALES DE VALOR ───────────────────────────────────────────────────────

_EV_UMBRAL_ALTO  = 0.10   # EV > 10% → ALTO
_EV_UMBRAL_MEDIO = 0.04   # EV > 4%  → MEDIO
_EV_UMBRAL_BAJO  = 0.00   # EV > 0%  → BAJO (tenue)

# Variación de cuota que activa circuit breaker (anomalía de mercado)
_CIRCUIT_BREAKER_VARIACION = 0.20   # 20% de cambio en < 60s


# ─── DATACLASSES ─────────────────────────────────────────────────────────────

@dataclass
class CuotasMercado:
    """Snapshot de cuotas back y lay para un partido."""
    match_id:       int
    ticker:         str
    fuente:         str
    timestamp:      float = field(default_factory=time.time)
    es_live:        bool = False
    minuto:         Optional[int] = None

    # Back (apostar A FAVOR)
    back_local:     float = 0.0
    back_empate:    float = 0.0
    back_visitante: float = 0.0

    # Lay (apostar EN CONTRA) — Brecha B
    lay_local:      Optional[float] = None
    lay_empate:     Optional[float] = None
    lay_visitante:  Optional[float] = None

    # Estado de conexión
    datos_frescos:  bool = True   # False → "posiblemente desactualizadas"


@dataclass
class AnalisisOdds:
    """Resultado del análisis de cuotas vs predicción IA."""
    ticker:      str
    resultado:   str     # "local" | "empate" | "visitante"
    prob_ia:     float
    cuota:       float
    ev:          float
    valor:       str     # "ALTO" | "MEDIO" | "BAJO" | "SIN_VALOR"
    market_inefficiency_gap: str
    overround:   float
    prob_impl:   float
    circuit_breaker_status: str = "OPERATIONAL"


# ─── OVERROUND CORRECTION ────────────────────────────────────────────────────

def probabilidades_implicitas(
    cuota_local: float,
    cuota_empate: float,
    cuota_visitante: float,
) -> tuple[float, float, float, float]:
    """
    Elimina el margen de la casa (overround) y devuelve probabilidades
    implícitas normalizadas que suman 1.

    Returns:
        (prob_local, prob_empate, prob_visitante, overround)
    """
    if any(c <= 1.0 for c in [cuota_local, cuota_empate, cuota_visitante]):
        raise ValueError("Todas las cuotas deben ser > 1.0")

    raw = [1 / cuota_local, 1 / cuota_empate, 1 / cuota_visitante]
    total = sum(raw)
    overround = total - 1.0

    norm = [r / total for r in raw]
    return norm[0], norm[1], norm[2], round(overround, 4)


# ─── VALOR ESPERADO ──────────────────────────────────────────────────────────

def calcular_ev(prob_ia: float, cuota_casa: float) -> float:
    """
    EV = (Probabilidad_IA × Cuota_Casa) − 1

    Si EV > 0 hay ineficiencia en la cuota: el mercado está subestimando
    la probabilidad real estimada por el modelo.
    """
    return round((prob_ia * cuota_casa) - 1.0, 4)


def clasificar_valor(ev: float) -> str:
    if ev >= _EV_UMBRAL_ALTO:
        return "ALTO"
    elif ev >= _EV_UMBRAL_MEDIO:
        return "MEDIO"
    elif ev > _EV_UMBRAL_BAJO:
        return "BAJO"
    return "SIN_VALOR"


def market_inefficiency_gap(ev: float) -> str:
    """Devuelve el gap de ineficiencia como porcentaje, para el output JSON."""
    return f"{round(ev * 100, 1)}%"


# ─── ANÁLISIS COMPLETO ───────────────────────────────────────────────────────

def analizar_cuotas(
    cuotas: CuotasMercado,
    prob_local_ia: float,
    prob_empate_ia: float,
    prob_visitante_ia: float,
    circuit_breaker_status: str = "OPERATIONAL",
) -> list[AnalisisOdds]:
    """
    Analiza los tres mercados (local/empate/visitante) y devuelve lista
    de señales ordenadas por EV descendente.
    """
    prob_impl_local, prob_impl_empate, prob_impl_visitante, overround = \
        probabilidades_implicitas(
            cuotas.back_local,
            cuotas.back_empate,
            cuotas.back_visitante,
        )

    mercados = [
        ("local",      prob_local_ia,     cuotas.back_local,     prob_impl_local),
        ("empate",     prob_empate_ia,    cuotas.back_empate,    prob_impl_empate),
        ("visitante",  prob_visitante_ia, cuotas.back_visitante, prob_impl_visitante),
    ]

    resultados = []
    for resultado, prob_ia, cuota, prob_impl in mercados:
        ev    = calcular_ev(prob_ia, cuota)
        valor = clasificar_valor(ev) if cuotas.datos_frescos else "DATOS_STALE"
        gap   = market_inefficiency_gap(ev)

        resultados.append(AnalisisOdds(
            ticker=cuotas.ticker,
            resultado=resultado,
            prob_ia=round(prob_ia * 100, 1),
            cuota=cuota,
            ev=ev,
            valor=valor,
            market_inefficiency_gap=gap,
            overround=overround,
            prob_impl=round(prob_impl * 100, 1),
            circuit_breaker_status=circuit_breaker_status,
        ))

    return sorted(resultados, key=lambda x: x.ev, reverse=True)


# ─── SPREAD BACK/LAY (BRECHA B) ──────────────────────────────────────────────

def calcular_spread_exchange(back: float, lay: float) -> dict:
    """
    Calcula el spread entre cuota back y lay en un exchange real.
    Un spread menor indica mayor liquidez.
    """
    if back <= 0 or lay <= 0 or lay <= back:
        return {"spread": None, "liquidez": "desconocida"}

    spread = lay - back
    spread_pct = (spread / back) * 100

    if spread_pct < 1:
        liquidez = "ALTA"
    elif spread_pct < 3:
        liquidez = "MEDIA"
    else:
        liquidez = "BAJA"

    return {
        "back": back,
        "lay": lay,
        "spread": round(spread, 3),
        "spread_pct": round(spread_pct, 2),
        "liquidez": liquidez,
    }


# ─── DETECCIÓN DE ANOMALÍA (CIRCUIT BREAKER INPUT) ───────────────────────────

class OddsChangeMonitor:
    """
    Detecta variaciones bruscas de cuota que deben congelar las alertas.
    Se usa como input para el circuit breaker bursátil de alertas (PDF 2).
    """

    def __init__(self):
        self._ultimo_snapshot: dict[str, dict] = {}   # ticker → {local, empate, visitante, ts}

    def registrar(self, cuotas: CuotasMercado) -> bool:
        """
        Registra las cuotas actuales y devuelve True si se detecta anomalía
        (variación > 20% en alguna cuota respecto al snapshot anterior).
        """
        key = cuotas.ticker
        ahora = {
            "local":     cuotas.back_local,
            "empate":    cuotas.back_empate,
            "visitante": cuotas.back_visitante,
            "ts":        cuotas.timestamp,
        }

        if key not in self._ultimo_snapshot:
            self._ultimo_snapshot[key] = ahora
            return False

        prev = self._ultimo_snapshot[key]
        anomalia = False

        for campo in ["local", "empate", "visitante"]:
            prev_val = prev.get(campo, 0)
            curr_val = ahora.get(campo, 0)
            if prev_val > 0:
                variacion = abs(curr_val - prev_val) / prev_val
                if variacion >= _CIRCUIT_BREAKER_VARIACION:
                    anomalia = True
                    break

        self._ultimo_snapshot[key] = ahora
        return anomalia


# Instancia global del monitor (en producción, usar Redis para compartir estado)
odds_monitor = OddsChangeMonitor()
