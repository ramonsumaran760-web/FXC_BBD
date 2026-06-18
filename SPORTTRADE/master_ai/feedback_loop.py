"""
feedback_loop.py — Brecha C: Auditoría y Reentrenamiento del Master AI.

Implementa:
  1. Registro de predicciones post-evento (backtesting_logs)
  2. Cálculo de Brier Score por agente
  3. Recalibración semanal de pesos via walk-forward validation
  4. Salvaguarda anti-overfitting: los nuevos pesos se validan antes de desplegarse
  5. Panel de rendimiento por agente

Proceso asíncrono: ejecutado semanalmente por Celery beat.
"""
from __future__ import annotations
import logging
import math
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger("fxcbbd.feedback_loop")

# ─── CONSTANTES ──────────────────────────────────────────────────────────────

_VENTANA_SEMANAS     = 12      # ventana móvil para calcular pesos
_MIN_PREDICCIONES    = 30      # mínimo de predicciones antes de recalibrar
_VALIDATION_SPLIT    = 0.25    # último 25% de la ventana = set de validación
_MAX_CAMBIO_PESO     = 0.30    # cambio máximo permitido por recalibración (±30%)
_BRIER_REF           = 0.25    # Brier Score de referencia (predictor aleatorio)

# Mapeo de resultado real a probabilidad objetivo para Brier Score
_RESULTADO_A_IDX = {"local": 0, "empate": 1, "visitante": 2}


# ─── BRIER SCORE ─────────────────────────────────────────────────────────────

def calcular_brier_score(
    prob_predicha: float,
    resultado_real: str,
    campo_predicho: str,   # "local" | "empate" | "visitante"
) -> float:
    """
    Brier Score = (p - o)²
    o = 1 si el campo predicho fue el resultado real, 0 si no.
    Rango [0, 1]: 0 = perfecto, 1 = peor que azar.
    """
    o = 1.0 if campo_predicho == resultado_real else 0.0
    return round((prob_predicha - o) ** 2, 6)


def calcular_brier_score_multiclase(
    prob_local: float,
    prob_empate: float,
    prob_visitante: float,
    resultado_real: str,
) -> float:
    """
    Brier Score multiclase: suma de (p_j - o_j)² para los 3 resultados.
    Normalizado: dividir por 3 para mantener escala [0, 1].
    """
    outcomes = {
        "local":     (prob_local,     1.0 if resultado_real == "local" else 0.0),
        "empate":    (prob_empate,     1.0 if resultado_real == "empate" else 0.0),
        "visitante": (prob_visitante,  1.0 if resultado_real == "visitante" else 0.0),
    }
    bs = sum((p - o) ** 2 for p, o in outcomes.values()) / 3
    return round(bs, 6)


# ─── REGISTRO DE PREDICCIÓN ──────────────────────────────────────────────────

def crear_log_prediccion(
    match_id: int,
    agente_id: str,
    prob_local: float,
    prob_empate: float,
    prob_visitante: float,
    confianza: float,
    features: Optional[dict] = None,
) -> dict:
    """
    Crea el registro para insertar en backtesting_logs.
    resultado_real y brier_score se llenan cuando el partido finaliza.
    """
    semana = datetime.utcnow().isocalendar()[1]
    return {
        "match_id":              match_id,
        "agente_id":             agente_id,
        "probabilidad_predicha": prob_local,   # prob del resultado que se recomienda
        "resultado_real":        None,          # se llena post-partido
        "confianza_declarada":   confianza,
        "prediccion_correcta":   None,
        "brier_score":           None,
        "fecha":                 datetime.utcnow(),
        "semana_iso":            semana,
        "features_entrada":      features or {},
        # Almacenamos las 3 probs para Brier Score multiclase
        "_prob_local":           prob_local,
        "_prob_empate":          prob_empate,
        "_prob_visitante":       prob_visitante,
    }


def cerrar_log_prediccion(log: dict, resultado_real: str) -> dict:
    """
    Completa el log post-partido: calcula Brier Score y acierto.
    """
    bs = calcular_brier_score_multiclase(
        log["_prob_local"],
        log["_prob_empate"],
        log["_prob_visitante"],
        resultado_real,
    )
    campo_predicho = _campo_con_mayor_prob(
        log["_prob_local"],
        log["_prob_empate"],
        log["_prob_visitante"],
    )
    log["resultado_real"]      = resultado_real
    log["prediccion_correcta"] = campo_predicho == resultado_real
    log["brier_score"]         = bs
    return log


def _campo_con_mayor_prob(p_l: float, p_e: float, p_v: float) -> str:
    probs = {"local": p_l, "empate": p_e, "visitante": p_v}
    return max(probs, key=lambda k: probs[k])


# ─── RECALIBRACIÓN DE PESOS — WALK-FORWARD ───────────────────────────────────

class RecalibradoPesos:
    """
    Calcula nuevos pesos para los 8 agentes según su desempeño histórico.

    Algoritmo:
    1. Tomar backtesting_logs de las últimas VENTANA_SEMANAS semanas
    2. Calcular Brier Score promedio por agente (entrenamiento: 75%)
    3. Derivar peso propuesto: inversamente proporcional al Brier Score
    4. Validar en el 25% restante: si el nuevo conjunto de pesos mejora
       el Brier Score del ensemble, desplegar; si no, mantener los actuales
    """

    def recalibrar(
        self,
        logs_por_agente: dict[str, list[dict]],
        pesos_actuales: dict[str, float],
    ) -> tuple[dict[str, float], dict]:
        """
        Args:
            logs_por_agente: {agente_id → [{"brier_score": ..., "semana_iso": ...}, ...]}
            pesos_actuales:  pesos actuales del Master AI

        Returns:
            (nuevos_pesos, reporte_calibracion)
        """
        n_agentes = len(logs_por_agente)
        if n_agentes == 0:
            return pesos_actuales, {"motivo": "sin_datos"}

        # ── Dividir en train / validation ────────────────────────────────────
        pesos_propuestos: dict[str, float] = {}
        brier_scores_agente: dict[str, float] = {}

        for agente_id, logs in logs_por_agente.items():
            if len(logs) < _MIN_PREDICCIONES:
                pesos_propuestos[agente_id] = pesos_actuales.get(agente_id, 1.0)
                logger.info("Agente %s: datos insuficientes (%d), manteniendo peso",
                            agente_id, len(logs))
                continue

            n_train = int(len(logs) * (1 - _VALIDATION_SPLIT))
            logs_train = logs[:n_train]

            bs_train = _brier_promedio(logs_train)
            brier_scores_agente[agente_id] = bs_train

            # Peso propuesto = inversamente proporcional al Brier Score
            # Si BS = 0 (perfecto) → peso máximo; BS = 0.25 (azar) → peso 1.0
            if bs_train <= 0:
                peso_raw = 2.0
            else:
                peso_raw = _BRIER_REF / bs_train   # normalizado al predictor aleatorio

            # Limitar cambio máximo respecto al peso actual
            peso_actual  = pesos_actuales.get(agente_id, 1.0)
            peso_propuesto = max(
                peso_actual * (1 - _MAX_CAMBIO_PESO),
                min(peso_actual * (1 + _MAX_CAMBIO_PESO), peso_raw),
            )
            pesos_propuestos[agente_id] = round(peso_propuesto, 4)

        # ── Walk-forward validation ───────────────────────────────────────────
        bs_actual    = self._evaluar_ensemble(logs_por_agente, pesos_actuales)
        bs_propuesto = self._evaluar_ensemble(logs_por_agente, pesos_propuestos, validation=True)

        if bs_propuesto < bs_actual:
            logger.info("Nuevos pesos aceptados: BS %.4f → %.4f", bs_actual, bs_propuesto)
            pesos_finales = pesos_propuestos
            desplegado    = True
        else:
            logger.warning("Nuevos pesos RECHAZADOS (BS %.4f ≥ actual %.4f) — manteniendo pesos",
                           bs_propuesto, bs_actual)
            pesos_finales = pesos_actuales
            desplegado    = False

        reporte = {
            "timestamp":        datetime.utcnow().isoformat(),
            "brier_score_antes": round(bs_actual, 5),
            "brier_score_tras":  round(bs_propuesto, 5),
            "desplegado":        desplegado,
            "pesos_finales":     pesos_finales,
            "brier_por_agente":  {k: round(v, 5) for k, v in brier_scores_agente.items()},
        }
        return pesos_finales, reporte

    def _evaluar_ensemble(
        self,
        logs_por_agente: dict[str, list[dict]],
        pesos: dict[str, float],
        validation: bool = False,
    ) -> float:
        """Evalúa el Brier Score del ensemble con los pesos dados."""
        all_bs = []
        for agente_id, logs in logs_por_agente.items():
            if validation:
                n_train = int(len(logs) * (1 - _VALIDATION_SPLIT))
                subset  = logs[n_train:]
            else:
                subset = logs

            peso = pesos.get(agente_id, 1.0)
            for log in subset:
                bs = log.get("brier_score")
                if bs is not None:
                    all_bs.append(bs * peso)

        return sum(all_bs) / len(all_bs) if all_bs else _BRIER_REF


def _brier_promedio(logs: list[dict]) -> float:
    scores = [l["brier_score"] for l in logs if l.get("brier_score") is not None]
    return sum(scores) / len(scores) if scores else _BRIER_REF


# ─── REPORTE DE CALIBRACIÓN ──────────────────────────────────────────────────

def generar_reporte_calibracion(
    logs_por_agente: dict[str, list[dict]],
) -> dict:
    """
    Genera el panel interno de evolución del acierto real por agente.
    Visible para el equipo de modelo (PDF 1 — Brecha C).
    """
    reporte: dict[str, dict] = {}
    for agente_id, logs in logs_por_agente.items():
        validos = [l for l in logs if l.get("brier_score") is not None]
        if not validos:
            continue

        aciertos = sum(1 for l in validos if l.get("prediccion_correcta"))
        bs_prom  = _brier_promedio(validos)

        reporte[agente_id] = {
            "total_predicciones": len(validos),
            "acierto_pct":        round(aciertos / len(validos) * 100, 1),
            "brier_score_prom":   round(bs_prom, 5),
            "mejor_que_azar":     bs_prom < _BRIER_REF,
            "skill_score":        round(1 - bs_prom / _BRIER_REF, 3),  # 1=perfecto, 0=azar, <0=peor que azar
        }
    return reporte


# Instancia global del calibrador
recalibrador = RecalibradoPesos()
