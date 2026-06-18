"""
master_ai.py — Agente 9: Supervisor / Master AI de FXC_BBD.

Rol: recibe las probabilidades de los 8 agentes especializados,
las combina usando una Matriz de Confianza ponderada dinámicamente
(los pesos se leen de agent_weights en BD y se recalibran semanalmente — Brecha C),
y produce el Output JSON unificado:

{
  "local": 58.2, "empate": 21.4, "visitante": 20.4,
  "confianza": 92,
  "valor": "ALTO",
  "meta_metrics": {
    "expected_value": 0.2222,
    "market_inefficiency_gap": "22%",
    "circuit_breaker_status": "OPERATIONAL"
  }
}
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Optional

from odds import calcular_ev, clasificar_valor, market_inefficiency_gap, CuotasMercado
from finanzas import calcular_fraccion_kelly, BankrollSettings, bankroll_manager
from live import circuit_breaker

logger = logging.getLogger("fxcbbd.master_ai")

# ─── PESOS POR DEFECTO (se sobreescriben con datos de BD) ────────────────────

PESOS_DEFAULT: dict[str, float] = {
    "agent_1_estadistica":  1.00,
    "agent_2_racha":        1.10,   # racha tiene ligero bonus por ser más reciente
    "agent_3_lesiones":     1.05,
    "agent_4_noticias":     0.60,   # menor confianza por subjetividad
    "agent_5_arbitro":      0.70,
    "agent_6_clima":        0.65,
    "agent_7_odds":         1.15,   # market intelligence = señal fuerte
    "agent_8_montecarlo":   1.20,   # modelo matemático = máximo peso
}


# ─── DATACLASSES ─────────────────────────────────────────────────────────────

@dataclass
class SalidaAgente:
    agente_id: str
    prob_local: float
    prob_empate: float
    prob_visitante: float
    confianza: float
    features: dict = field(default_factory=dict)


@dataclass
class OutputMasterAI:
    """Output JSON unificado del Master AI — formato exacto del PDF 2."""
    ticker: str
    local: float              # probabilidad % (ej. 58.2)
    empate: float
    visitante: float
    confianza: float          # 0-100
    valor: str                # "ALTO" | "MEDIO" | "BAJO" | "SIN_VALOR"
    meta_metrics: dict        # EV, gap, circuit_breaker_status
    contribuciones: dict      # prob de cada agente
    pesos_usados: dict        # peso efectivo de cada agente
    # Brecha A — Kelly
    kelly_fraccion: Optional[float] = None
    monto_sugerido_pct: Optional[float] = None
    resultado_recomendado: Optional[str] = None

    def to_json(self) -> dict:
        base = {
            "ticker": self.ticker,
            "local": self.local,
            "empate": self.empate,
            "visitante": self.visitante,
            "confianza": self.confianza,
            "valor": self.valor,
            "meta_metrics": self.meta_metrics,
        }
        if self.kelly_fraccion is not None:
            base["kelly"] = {
                "fraccion": self.kelly_fraccion,
                "monto_pct": self.monto_sugerido_pct,
                "resultado_rec": self.resultado_recomendado,
            }
        return base


# ─── MOTOR MASTER AI ─────────────────────────────────────────────────────────

class MasterAI:
    """
    Agente 9: Supervisor del ensemble de 8 agentes.
    Aplica Matriz de Confianza y produce el output unificado.
    """

    def __init__(self, pesos: Optional[dict[str, float]] = None):
        self._pesos = pesos or PESOS_DEFAULT.copy()

    def actualizar_pesos(self, nuevos_pesos: dict[str, float]):
        """Recibe los pesos recalibrados desde feedback_loop.py."""
        self._pesos.update(nuevos_pesos)
        logger.info("Pesos del Master AI actualizados: %s", nuevos_pesos)

    def procesar(
        self,
        ticker: str,
        salidas_agentes: list[SalidaAgente],
        cuotas: Optional[CuotasMercado] = None,
        bankroll: Optional[BankrollSettings] = None,
        eventos_activos_liga: int = 0,
    ) -> OutputMasterAI:
        """
        Pipeline principal del Master AI:
        1. Combina probabilidades con pesos × confianza
        2. Calcula EV con las cuotas de mercado
        3. Clasifica valor (ALTO/MEDIO/BAJO)
        4. Calcula Kelly si bankroll disponible (Brecha A)
        5. Verifica circuit breaker
        """
        if not salidas_agentes:
            return self._output_sin_datos(ticker)

        # ── Paso 1: Matriz de Confianza ponderada ────────────────────────────
        prob_local, prob_empate, prob_visitante, pesos_efectivos = \
            self._combinar_probabilidades(salidas_agentes)

        confianza_ensemble = self._calcular_confianza_ensemble(salidas_agentes, pesos_efectivos)

        # ── Paso 2: EV y clasificación de valor ──────────────────────────────
        resultado_rec, ev, cuota_rec = None, None, None
        valor = "SIN_VALOR"
        gap   = "0%"
        cb_status = circuit_breaker.estado

        if cuotas and cuotas.datos_frescos and circuit_breaker.permite_alerta():
            prob_ia_map = {
                "local":     prob_local,
                "empate":    prob_empate,
                "visitante": prob_visitante,
            }
            cuota_map = {
                "local":     cuotas.back_local,
                "empate":    cuotas.back_empate,
                "visitante": cuotas.back_visitante,
            }

            best_ev   = -999
            for resultado, p_ia in prob_ia_map.items():
                cuota = cuota_map.get(resultado, 0)
                if cuota > 1:
                    ev_resultado = calcular_ev(p_ia, cuota)
                    if ev_resultado > best_ev:
                        best_ev      = ev_resultado
                        resultado_rec = resultado
                        ev            = ev_resultado
                        cuota_rec     = cuota

            if ev is not None:
                valor = clasificar_valor(ev)
                gap   = market_inefficiency_gap(ev)
        elif not circuit_breaker.permite_alerta():
            valor     = "CONGELADO"
            cb_status = circuit_breaker.estado
        elif cuotas and not cuotas.datos_frescos:
            valor     = "DATOS_STALE"

        # ── Paso 3: Kelly (Brecha A) ──────────────────────────────────────────
        kelly_fraccion     = None
        monto_sugerido_pct = None

        if bankroll and resultado_rec and ev and ev > 0 and cuota_rec:
            prob_rec = prob_ia_map.get(resultado_rec, 0)
            kelly_fraccion = calcular_fraccion_kelly(
                prob_rec, cuota_rec, bankroll.perfil_riesgo
            )
            monto_sugerido_pct = round(kelly_fraccion * 100, 2)

        # ── Paso 4: Construir Output ──────────────────────────────────────────
        contribuciones = {
            s.agente_id: {
                "prob_local": s.prob_local,
                "prob_empate": s.prob_empate,
                "prob_visitante": s.prob_visitante,
                "confianza": s.confianza,
            }
            for s in salidas_agentes
        }

        return OutputMasterAI(
            ticker=ticker,
            local=round(prob_local * 100, 1),
            empate=round(prob_empate * 100, 1),
            visitante=round(prob_visitante * 100, 1),
            confianza=round(confianza_ensemble * 100, 1),
            valor=valor,
            meta_metrics={
                "expected_value": round(ev, 4) if ev is not None else None,
                "market_inefficiency_gap": gap,
                "circuit_breaker_status": cb_status,
                "resultado_recomendado": resultado_rec,
                "cuota_recomendada": cuota_rec,
                "datos_frescos": cuotas.datos_frescos if cuotas else None,
            },
            contribuciones=contribuciones,
            pesos_usados=pesos_efectivos,
            kelly_fraccion=kelly_fraccion,
            monto_sugerido_pct=monto_sugerido_pct,
            resultado_recomendado=resultado_rec,
        )

    def _combinar_probabilidades(
        self,
        salidas: list[SalidaAgente],
    ) -> tuple[float, float, float, dict]:
        """
        Combina probabilidades usando:
        peso_efectivo = peso_base × confianza_agente
        Normaliza la suma de pesos efectivos.
        """
        suma_local = suma_empate = suma_visitante = suma_pesos = 0.0
        pesos_efectivos: dict[str, float] = {}

        for s in salidas:
            peso_base    = self._pesos.get(s.agente_id, 1.0)
            peso_efectivo = peso_base * s.confianza
            pesos_efectivos[s.agente_id] = round(peso_efectivo, 4)

            suma_local     += s.prob_local * peso_efectivo
            suma_empate    += s.prob_empate * peso_efectivo
            suma_visitante += s.prob_visitante * peso_efectivo
            suma_pesos     += peso_efectivo

        if suma_pesos == 0:
            return 0.40, 0.28, 0.32, {}

        prob_local     = suma_local / suma_pesos
        prob_empate    = suma_empate / suma_pesos
        prob_visitante = suma_visitante / suma_pesos

        # Renormalizar para que sumen exactamente 1
        total = prob_local + prob_empate + prob_visitante
        return prob_local / total, prob_empate / total, prob_visitante / total, pesos_efectivos

    def _calcular_confianza_ensemble(
        self,
        salidas: list[SalidaAgente],
        pesos_efectivos: dict[str, float],
    ) -> float:
        """
        Confianza del ensemble = media ponderada de confianzas individuales.
        Se penaliza si hay alta dispersión entre agentes.
        """
        if not salidas:
            return 0.0

        total_peso = sum(pesos_efectivos.values())
        if total_peso == 0:
            return 0.0

        conf_pond = sum(
            s.confianza * pesos_efectivos.get(s.agente_id, 1.0)
            for s in salidas
        ) / total_peso

        # Penalización por dispersión (desacuerdo entre agentes)
        probs_local = [s.prob_local for s in salidas]
        dispersion = max(probs_local) - min(probs_local)
        penalizacion = min(0.15, dispersion * 0.5)

        return max(0.0, min(1.0, conf_pond - penalizacion))

    def _output_sin_datos(self, ticker: str) -> OutputMasterAI:
        return OutputMasterAI(
            ticker=ticker,
            local=40.0, empate=28.0, visitante=32.0,
            confianza=0.0,
            valor="SIN_DATOS",
            meta_metrics={"circuit_breaker_status": "OPERATIONAL"},
            contribuciones={},
            pesos_usados={},
        )


# Instancia global
master_ai = MasterAI()
