"""
montecarlo.py — Simulador Monte Carlo de FXC_BBD (Agente 8).

Implementa simulación Poisson de goles/tarjetas con:
  • 10 000 a 100 000 iteraciones configurables
  • Paralelización via concurrent.futures (CPU) o Celery (distribuido)
  • Objetivo: < 50ms por partido en vivo
  • Output: probabilidades de resultado + distribución de goles
"""
from __future__ import annotations
import asyncio
import math
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from typing import Optional
import random


# ─── CONFIGURACIÓN ───────────────────────────────────────────────────────────

_N_ITER_LIVE  = 10_000    # Iteraciones para partidos en vivo (velocidad)
_N_ITER_PREV  = 50_000    # Iteraciones para análisis previo al partido
_N_ITER_MAX   = 100_000   # Máximo (análisis de alta precisión)
_TARGET_MS    = 50        # Objetivo de latencia en ms


# ─── DISTRIBUCIÓN POISSON ────────────────────────────────────────────────────

def _poisson_sample(lam: float) -> int:
    """Muestreo Poisson con método de Knuth (sin scipy para velocidad máxima)."""
    if lam <= 0:
        return 0
    L = math.exp(-lam)
    k = 0
    p = 1.0
    while p > L:
        k += 1
        p *= random.random()
    return k - 1


def _simular_bloque(args: tuple) -> tuple[int, int, int]:
    """
    Simula n_iter partidos y devuelve (victorias_local, empates, victorias_visit).
    Diseñado para ejecutarse en subprocesos paralelos.
    """
    xg_local, xg_visit, n_iter = args
    vic_local = vic_empate = vic_visit = 0
    for _ in range(n_iter):
        g_l = _poisson_sample(xg_local)
        g_v = _poisson_sample(xg_visit)
        if g_l > g_v:
            vic_local += 1
        elif g_l == g_v:
            vic_empate += 1
        else:
            vic_visit += 1
    return vic_local, vic_empate, vic_visit


# ─── DATACLASS DE RESULTADO ──────────────────────────────────────────────────

@dataclass
class ResultadoMonteCarlo:
    prob_local:     float
    prob_empate:    float
    prob_visitante: float
    xg_local:       float
    xg_visit:       float
    iteraciones:    int
    duracion_ms:    float
    confianza:      float    # 0-1 basado en convergencia estadística
    distribucion_goles: dict  # {0: 0.12, 1: 0.28, ...}


# ─── MOTOR PRINCIPAL ─────────────────────────────────────────────────────────

def simular_partido(
    xg_local: float,
    xg_visit: float,
    n_iter: int = _N_ITER_LIVE,
    paralelo: bool = False,
    n_workers: int = 4,
) -> ResultadoMonteCarlo:
    """
    Simula n_iter partidos vía Poisson y devuelve distribución de resultados.

    Args:
        xg_local:  Expected Goals del equipo local
        xg_visit:  Expected Goals del equipo visitante
        n_iter:    Número de iteraciones (10k-100k)
        paralelo:  Usar ProcessPoolExecutor para máxima velocidad
        n_workers: Número de workers paralelos
    """
    t0 = time.perf_counter()

    if paralelo and n_iter >= _N_ITER_PREV:
        vic_l, vic_e, vic_v = _simular_paralelo(xg_local, xg_visit, n_iter, n_workers)
    else:
        vic_l, vic_e, vic_v = _simular_bloque((xg_local, xg_visit, n_iter))

    prob_local     = vic_l / n_iter
    prob_empate    = vic_e / n_iter
    prob_visitante = vic_v / n_iter

    duracion_ms = (time.perf_counter() - t0) * 1000

    # Confianza estadística: estimada por error estándar de proporción
    # SE = sqrt(p(1-p)/n); confianza ≈ 1 − SE/p (simplificado)
    se_max = math.sqrt(0.25 / n_iter)  # peor caso: p=0.5
    confianza = max(0.0, min(1.0, 1.0 - se_max * 10))

    return ResultadoMonteCarlo(
        prob_local=round(prob_local, 4),
        prob_empate=round(prob_empate, 4),
        prob_visitante=round(prob_visitante, 4),
        xg_local=xg_local,
        xg_visit=xg_visit,
        iteraciones=n_iter,
        duracion_ms=round(duracion_ms, 2),
        confianza=round(confianza, 3),
        distribucion_goles=_distribucion_goles(xg_local, xg_visit),
    )


def _simular_paralelo(
    xg_local: float,
    xg_visit: float,
    n_iter: int,
    n_workers: int,
) -> tuple[int, int, int]:
    """Divide las iteraciones entre workers y agrega resultados."""
    bloque = n_iter // n_workers
    args = [(xg_local, xg_visit, bloque)] * n_workers

    with ProcessPoolExecutor(max_workers=n_workers) as executor:
        resultados = list(executor.map(_simular_bloque, args))

    vic_l = sum(r[0] for r in resultados)
    vic_e = sum(r[1] for r in resultados)
    vic_v = sum(r[2] for r in resultados)
    return vic_l, vic_e, vic_v


def _distribucion_goles(xg_local: float, xg_visit: float, max_goles: int = 6) -> dict:
    """
    Calcula la distribución de probabilidad de goles totales
    (combinando Poisson local + visitante).
    """
    dist = {}
    for total in range(max_goles + 1):
        prob = 0.0
        for g_l in range(total + 1):
            g_v = total - g_l
            # P(X=k) = e^(-λ) * λ^k / k!
            p_l = _poisson_pmf(xg_local, g_l)
            p_v = _poisson_pmf(xg_visit, g_v)
            prob += p_l * p_v
        dist[str(total)] = round(prob, 4)
    return dist


def _poisson_pmf(lam: float, k: int) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    log_pmf = -lam + k * math.log(lam) - sum(math.log(i) for i in range(1, k + 1))
    return math.exp(log_pmf)


# ─── XG ESTIMATOR (SIN DATOS EXTERNOS) ───────────────────────────────────────

def estimar_xg(
    goles_prom_local_ataque: float,   # promedio goles anotados en casa
    goles_prom_local_defensa: float,  # promedio goles recibidos en casa
    goles_prom_visit_ataque: float,   # promedio goles anotados de visitante
    goles_prom_visit_defensa: float,  # promedio goles recibidos de visitante
    factor_local: float = 1.10,       # ventaja de jugar en casa
) -> tuple[float, float]:
    """
    Estima Expected Goals usando el modelo Dixon-Coles simplificado.
    xg_local  = (ataque_local  / media_liga) × (defensa_visit / media_liga) × media_liga × factor_local
    """
    media_liga = 1.35   # promedio histórico de goles por equipo en La Liga / Premier
    xg_l = (goles_prom_local_ataque / media_liga) * \
           (goles_prom_visit_defensa / media_liga) * \
           media_liga * factor_local
    xg_v = (goles_prom_visit_ataque / media_liga) * \
           (goles_prom_local_defensa / media_liga) * \
           media_liga
    return round(max(0.1, xg_l), 3), round(max(0.1, xg_v), 3)


# ─── SIMULACIÓN ASYNC (PARA FASTAPI) ─────────────────────────────────────────

async def simular_partido_async(
    xg_local: float,
    xg_visit: float,
    n_iter: int = _N_ITER_LIVE,
) -> ResultadoMonteCarlo:
    """Versión async: corre la simulación en executor para no bloquear el event loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: simular_partido(xg_local, xg_visit, n_iter, paralelo=False),
    )
