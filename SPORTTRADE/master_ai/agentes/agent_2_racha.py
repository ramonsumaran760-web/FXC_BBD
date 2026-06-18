"""
Agente 2 — Racha y Forma Reciente.
Analiza los últimos 5 partidos de cada equipo, aplicando
mayor peso a los más recientes (factor de descuento temporal).
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal


ResultadoPartido = Literal["W", "D", "L"]


@dataclass
class FormaReciente:
    nombre: str
    ultimos_5: list[ResultadoPartido]   # más reciente primero
    goles_anotados: list[int]           # goles en cada uno de esos 5 partidos
    goles_recibidos: list[int]


_PESOS_TEMPORALES = [0.35, 0.25, 0.20, 0.12, 0.08]   # mayor peso al partido más reciente
_PUNTOS = {"W": 3, "D": 1, "L": 0}


def calcular(forma_local: FormaReciente, forma_visit: FormaReciente) -> dict:
    """
    Calcula probabilidades según la forma reciente de ambos equipos.
    Pondera cada resultado según su antigüedad (decay temporal).
    """
    score_local = _score_forma(forma_local)
    score_visit = _score_forma(forma_visit)

    # Momentum: diferencia de tendencia en los 3 últimos vs los 2 anteriores
    momentum_local = _momentum(forma_local)
    momentum_visit = _momentum(forma_visit)

    # Ajustar scores con momentum
    score_local  *= (1 + momentum_local * 0.15)
    score_visit  *= (1 + momentum_visit * 0.15)
    total = score_local + score_visit + 0.001

    prob_local     = score_local / total * 0.72   # reservar margen para empate
    prob_visitante = score_visit / total * 0.72
    prob_empate    = 1 - prob_local - prob_visitante

    # Normalizar
    total_p = prob_local + prob_empate + prob_visitante
    prob_local     /= total_p
    prob_empate    /= total_p
    prob_visitante /= total_p

    confianza = 0.78 if len(forma_local.ultimos_5) >= 5 else 0.45

    return {
        "agente_id": "agent_2_racha",
        "prob_local": round(prob_local, 4),
        "prob_empate": round(prob_empate, 4),
        "prob_visitante": round(prob_visitante, 4),
        "confianza": confianza,
        "features": {
            "score_forma_local": round(score_local, 3),
            "score_forma_visit": round(score_visit, 3),
            "momentum_local": round(momentum_local, 3),
            "momentum_visit": round(momentum_visit, 3),
            "racha_local": "".join(forma_local.ultimos_5),
            "racha_visit": "".join(forma_visit.ultimos_5),
        },
    }


def _score_forma(forma: FormaReciente) -> float:
    """Score ponderado temporalmente de la forma reciente."""
    score = 0.0
    for i, resultado in enumerate(forma.ultimos_5[:5]):
        peso = _PESOS_TEMPORALES[i] if i < len(_PESOS_TEMPORALES) else 0.05
        puntos = _PUNTOS.get(resultado, 0)
        score += puntos * peso
    return max(score, 0.01)


def _momentum(forma: FormaReciente) -> float:
    """
    Tendencia: compara forma en últimos 3 vs anteriores 2.
    Positivo = equipo mejorando. Negativo = decayendo.
    """
    if len(forma.ultimos_5) < 5:
        return 0.0
    recientes  = sum(_PUNTOS.get(r, 0) for r in forma.ultimos_5[:3]) / 3
    anteriores = sum(_PUNTOS.get(r, 0) for r in forma.ultimos_5[3:]) / 2
    max_pts = 3.0
    return (recientes - anteriores) / max_pts
