"""
Agente 7 — Movimiento de Cuotas (Market Intelligence).
Analiza la variación temporal de cuotas para detectar:
  • Dinero inteligente (sharp money): caída brusca de cuota sin razón pública
  • CLV (Closing Line Value): si el modelo predicó una cuota que luego cerró menor
  • Consenso de mercado: distribución del movimiento entre casas
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SnapshotOdds:
    """Instantánea de cuotas en un momento dado."""
    timestamp: float
    back_local: float
    back_empate: float
    back_visitante: float


@dataclass
class MovimientoMercado:
    ticker: str
    apertura: SnapshotOdds            # cuotas al abrir el mercado
    actual: SnapshotOdds              # cuotas actuales
    volumen_relativo: float = 1.0     # 1.0 = volumen normal; >1.5 = volumen inusual
    num_casas: int = 5                # número de casas comparadas


def calcular(movimiento: MovimientoMercado) -> dict:
    """
    Interpreta el movimiento de cuotas como señal de información privilegiada.

    Si la cuota del local cayó > 8% → dinero sharp en local.
    Esto es información independiente del modelo y aumenta la confianza.
    """
    # Calcular variación porcentual de cada cuota
    var_local = _variacion(movimiento.apertura.back_local, movimiento.actual.back_local)
    var_empate = _variacion(movimiento.apertura.back_empate, movimiento.actual.back_empate)
    var_visit  = _variacion(movimiento.apertura.back_visitante, movimiento.actual.back_visitante)

    # Probabilidades implícitas actuales (overround simple)
    raw = [1/movimiento.actual.back_local,
           1/movimiento.actual.back_empate,
           1/movimiento.actual.back_visitante]
    total = sum(raw)
    prob_local     = raw[0] / total
    prob_empate    = raw[1] / total
    prob_visitante = raw[2] / total

    # Detectar dinero sharp (movimiento > 8% sin explicación pública)
    sharp_local     = var_local  < -0.08
    sharp_empate    = var_empate < -0.08
    sharp_visitante = var_visit  < -0.08

    # Ajuste por dinero sharp: amplificar la señal del mercado
    if sharp_local:
        prob_local *= 1.05
    if sharp_visitante:
        prob_visitante *= 1.05

    total_p = prob_local + prob_empate + prob_visitante
    prob_local     /= total_p
    prob_empate    /= total_p
    prob_visitante /= total_p

    # Confianza: mayor si hay movimiento significativo y volumen alto
    movimiento_max = max(abs(var_local), abs(var_empate), abs(var_visit))
    confianza = min(0.90, 0.50 + movimiento_max * 2 + (movimiento.volumen_relativo - 1) * 0.1)

    return {
        "agente_id": "agent_7_odds",
        "prob_local": round(prob_local, 4),
        "prob_empate": round(prob_empate, 4),
        "prob_visitante": round(prob_visitante, 4),
        "confianza": round(confianza, 3),
        "features": {
            "variacion_local_pct": round(var_local * 100, 1),
            "variacion_empate_pct": round(var_empate * 100, 1),
            "variacion_visit_pct": round(var_visit * 100, 1),
            "sharp_money_local": sharp_local,
            "sharp_money_empate": sharp_empate,
            "sharp_money_visitante": sharp_visitante,
            "volumen_relativo": movimiento.volumen_relativo,
        },
    }


def _variacion(apertura: float, actual: float) -> float:
    """Variación porcentual: negativo = cuota bajó (más demanda sobre ese resultado)."""
    if apertura <= 0:
        return 0.0
    return (actual - apertura) / apertura
