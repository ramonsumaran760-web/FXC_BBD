"""
Agente 5 — Árbitro y Contexto Disciplinario.
Evalúa el historial del árbitro designado: tarjetas, penaltis,
favoritismo local/visitante y tendencia en partidos de alta tensión.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class PerfilArbitro:
    nombre: str
    partidos_arbitrados: int
    tarjetas_amarillas_prom: float   # por partido
    tarjetas_rojas_prom: float
    penaltis_prom: float
    tasa_victoria_local: float       # % de veces que ganó el equipo local
    tasa_empate: float
    es_estricto: bool = False        # árbitros estrictos → menos goles, más tarjetas


def calcular(arbitro: PerfilArbitro) -> dict:
    """
    Ajusta probabilidades según perfil del árbitro.
    Un árbitro con alta tasa de victoria local confirma/amplifica la ventaja de local.
    Un árbitro "estricto" tiende a más empates (juego interrumpido).
    """
    if arbitro.partidos_arbitrados < 10:
        return _output_neutro()

    # El árbitro confirma o penaliza la ventaja de local
    # tasa_victoria_local media histórica ≈ 0.44
    sesgo_local = (arbitro.tasa_victoria_local - 0.44) * 0.2

    prob_local     = 0.40 + sesgo_local
    prob_empate    = arbitro.tasa_empate
    prob_visitante = 1.0 - prob_local - prob_empate

    # Árbitros estrictos → más interrupciones → ligero aumento de empates
    if arbitro.es_estricto:
        prob_empate    += 0.02
        prob_local     -= 0.01
        prob_visitante -= 0.01

    prob_local     = max(0.05, min(0.85, prob_local))
    prob_visitante = max(0.05, min(0.85, prob_visitante))
    prob_empate    = max(0.05, min(0.70, prob_empate))

    total = prob_local + prob_empate + prob_visitante
    prob_local     /= total
    prob_empate    /= total
    prob_visitante /= total

    confianza = min(0.80, arbitro.partidos_arbitrados / 100) * 0.70

    return {
        "agente_id": "agent_5_arbitro",
        "prob_local": round(prob_local, 4),
        "prob_empate": round(prob_empate, 4),
        "prob_visitante": round(prob_visitante, 4),
        "confianza": round(confianza, 3),
        "features": {
            "arbitro": arbitro.nombre,
            "tasa_victoria_local": arbitro.tasa_victoria_local,
            "tasa_empate": arbitro.tasa_empate,
            "tarjetas_prom": arbitro.tarjetas_amarillas_prom,
            "penaltis_prom": arbitro.penaltis_prom,
            "es_estricto": arbitro.es_estricto,
        },
    }


def _output_neutro() -> dict:
    return {
        "agente_id": "agent_5_arbitro",
        "prob_local": 0.40,
        "prob_empate": 0.28,
        "prob_visitante": 0.32,
        "confianza": 0.15,
        "features": {"motivo": "datos_insuficientes"},
    }
