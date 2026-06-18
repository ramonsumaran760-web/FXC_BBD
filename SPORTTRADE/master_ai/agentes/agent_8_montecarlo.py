"""
Agente 8 — Monte Carlo (wrapper del simulador).
Interfaz del motor montecarlo.py para el pipeline del Master AI.
Estima xG a partir de estadísticas del partido y lanza la simulación.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import asyncio

from montecarlo import simular_partido, estimar_xg, ResultadoMonteCarlo, _N_ITER_LIVE, _N_ITER_PREV


@dataclass
class InputMonteCarlo:
    goles_prom_local_ataque:  float
    goles_prom_local_defensa: float
    goles_prom_visit_ataque:  float
    goles_prom_visit_defensa: float
    es_live: bool = False
    xg_local_override: Optional[float] = None    # Si vienen de Opta/Statsbomb
    xg_visit_override: Optional[float] = None


def calcular(input_mc: InputMonteCarlo) -> dict:
    """
    Lanza la simulación Monte Carlo y convierte el resultado al formato del pipeline.
    En partidos live: 10k iteraciones (velocidad).
    En análisis previo: 50k iteraciones (precisión).
    """
    if input_mc.xg_local_override and input_mc.xg_visit_override:
        xg_local = input_mc.xg_local_override
        xg_visit = input_mc.xg_visit_override
    else:
        xg_local, xg_visit = estimar_xg(
            input_mc.goles_prom_local_ataque,
            input_mc.goles_prom_local_defensa,
            input_mc.goles_prom_visit_ataque,
            input_mc.goles_prom_visit_defensa,
        )

    n_iter = _N_ITER_LIVE if input_mc.es_live else _N_ITER_PREV
    resultado: ResultadoMonteCarlo = simular_partido(xg_local, xg_visit, n_iter)

    return {
        "agente_id": "agent_8_montecarlo",
        "prob_local": resultado.prob_local,
        "prob_empate": resultado.prob_empate,
        "prob_visitante": resultado.prob_visitante,
        "confianza": resultado.confianza,
        "features": {
            "xg_local": xg_local,
            "xg_visit": xg_visit,
            "iteraciones": resultado.iteraciones,
            "duracion_ms": resultado.duracion_ms,
            "distribucion_goles": resultado.distribucion_goles,
        },
    }
