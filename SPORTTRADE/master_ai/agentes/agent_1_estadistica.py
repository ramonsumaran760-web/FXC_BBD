"""
Agente 1 — Estadística General.
Analiza rendimiento histórico de ambos equipos:
goles anotados/recibidos, puntos, xG promedio, posición en tabla.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class EstadisticaEquipo:
    nombre: str
    pj: int              # partidos jugados
    pg: int              # partidos ganados
    pe: int              # empatados
    pp: int              # perdidos
    gf: int              # goles a favor
    gc: int              # goles en contra
    xg_prom: float       # Expected Goals promedio por partido
    xgc_prom: float      # Expected Goals concedidos promedio
    posicion_tabla: int  # posición en la liga


def calcular(
    stats_local: EstadisticaEquipo,
    stats_visit: EstadisticaEquipo,
) -> dict:
    """
    Calcula probabilidades basadas en estadísticas históricas.
    Usa modelo de cuotas comparativas por rendimiento relativo.
    """
    if stats_local.pj == 0 or stats_visit.pj == 0:
        return _output_neutro()

    # Tasas de victoria normalizadas
    win_rate_local = stats_local.pg / stats_local.pj
    win_rate_visit = stats_visit.pg / stats_visit.pj
    draw_rate_local = stats_local.pe / stats_local.pj

    # Potencia ofensiva/defensiva relativa
    ataque_local  = stats_local.gf / max(stats_local.pj, 1)
    defensa_local = stats_local.gc / max(stats_local.pj, 1)
    ataque_visit  = stats_visit.gf / max(stats_visit.pj, 1)
    defensa_visit = stats_visit.gc / max(stats_visit.pj, 1)

    # Score compuesto (mayor = mejor equipo local)
    score_local = (win_rate_local * 0.5 + ataque_local * 0.3 - defensa_local * 0.2)
    score_visit = (win_rate_visit * 0.5 + ataque_visit * 0.3 - defensa_visit * 0.2)
    score_total = score_local + score_visit + 0.001

    prob_local     = score_local / score_total
    prob_visitante = score_visit / score_total
    # Empate: promedio de tasas de empate, ajustado
    prob_empate = (draw_rate_local + (1 - win_rate_local - draw_rate_local) * 0.3)

    # Normalizar
    total = prob_local + prob_empate + prob_visitante
    prob_local     /= total
    prob_empate    /= total
    prob_visitante /= total

    # Confianza basada en muestra estadística
    confianza = min(1.0, (stats_local.pj + stats_visit.pj) / 80) * 0.85

    return {
        "agente_id": "agent_1_estadistica",
        "prob_local": round(prob_local, 4),
        "prob_empate": round(prob_empate, 4),
        "prob_visitante": round(prob_visitante, 4),
        "confianza": round(confianza, 3),
        "features": {
            "win_rate_local": round(win_rate_local, 3),
            "win_rate_visit": round(win_rate_visit, 3),
            "xg_prom_local": stats_local.xg_prom,
            "xg_prom_visit": stats_visit.xg_prom,
        },
    }


def _output_neutro() -> dict:
    return {
        "agente_id": "agent_1_estadistica",
        "prob_local": 0.40,
        "prob_empate": 0.28,
        "prob_visitante": 0.32,
        "confianza": 0.1,
        "features": {},
    }
