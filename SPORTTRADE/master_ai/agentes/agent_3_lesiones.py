"""
Agente 3 — Lesiones y Suspensiones.
Evalúa el impacto de bajas en la alineación titular estimada.
Cada posición tiene un peso de impacto diferente (portero > defensa > centrocampista > delantero).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal

Posicion = Literal["portero", "defensa", "centrocampista", "delantero"]

_IMPACTO_POSICION = {
    "portero":         0.18,
    "defensa":         0.12,
    "centrocampista":  0.09,
    "delantero":       0.11,
}

_IMPACTO_TITULAR_VS_SUPLENTE = 1.8   # titular ausente pesa más


@dataclass
class Baja:
    nombre: str
    posicion: Posicion
    es_titular: bool = True
    nivel_impacto: float = 1.0   # 0-1: 1 = jugador clave, 0.5 = suplente habitual


@dataclass
class ReporteLesiones:
    equipo: str
    bajas: list[Baja] = field(default_factory=list)


def calcular(reporte_local: ReporteLesiones, reporte_visit: ReporteLesiones) -> dict:
    """
    Cuantifica el impacto de las bajas en la probabilidad de resultado.
    Una baja de portero titular impacta más que 3 suplentes de campo.
    """
    penalidad_local = _calcular_penalidad(reporte_local.bajas)
    penalidad_visit = _calcular_penalidad(reporte_visit.bajas)

    # Probabilidades base (neutral)
    prob_local     = 0.40 - penalidad_local + penalidad_visit * 0.5
    prob_visitante = 0.32 - penalidad_visit + penalidad_local * 0.5
    prob_empate    = 1.0 - prob_local - prob_visitante

    # Clamp
    prob_local     = max(0.05, min(0.85, prob_local))
    prob_visitante = max(0.05, min(0.85, prob_visitante))
    prob_empate    = max(0.05, min(0.70, prob_empate))

    # Normalizar
    total = prob_local + prob_empate + prob_visitante
    prob_local     /= total
    prob_empate    /= total
    prob_visitante /= total

    total_bajas = len(reporte_local.bajas) + len(reporte_visit.bajas)
    confianza = 0.82 if total_bajas > 0 else 0.35   # sin datos de lesiones → baja confianza

    return {
        "agente_id": "agent_3_lesiones",
        "prob_local": round(prob_local, 4),
        "prob_empate": round(prob_empate, 4),
        "prob_visitante": round(prob_visitante, 4),
        "confianza": confianza,
        "features": {
            "penalidad_local": round(penalidad_local, 4),
            "penalidad_visit": round(penalidad_visit, 4),
            "bajas_local": len(reporte_local.bajas),
            "bajas_visit": len(reporte_visit.bajas),
            "baja_portero_local": any(b.posicion == "portero" for b in reporte_local.bajas),
            "baja_portero_visit": any(b.posicion == "portero" for b in reporte_visit.bajas),
        },
    }


def _calcular_penalidad(bajas: list[Baja]) -> float:
    penalidad = 0.0
    for baja in bajas:
        base = _IMPACTO_POSICION.get(baja.posicion, 0.08)
        mult = _IMPACTO_TITULAR_VS_SUPLENTE if baja.es_titular else 1.0
        penalidad += base * mult * baja.nivel_impacto
    return min(penalidad, 0.35)   # cap: ningún equipo pierde más de 35% de prob por lesiones
