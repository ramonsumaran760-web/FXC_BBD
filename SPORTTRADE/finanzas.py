"""
finanzas.py — Motor financiero de FXC_BBD.

Brecha A implementada:
  • calcular_fraccion_kelly()  — Kelly fraccionado por perfil de riesgo
  • bankroll_manager()         — dimensionamiento completo de posición
  • ajuste_correlacion()       — reduce exposición en eventos del mismo torneo
  • calcular_trading_out()     — stake lay para neutralizar posición abierta (Brecha B)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import math

# ─── CONSTANTES DE PERFIL ────────────────────────────────────────────────────

_KELLY_DIVISOR = {
    "conservador": 4,   # 1/4 Kelly
    "moderado":    2,   # 1/2 Kelly
    "agresivo":    1,   # Kelly completo
}

_MAX_EXP_EVENTO = {
    "conservador": 0.04,   # 4% máximo por evento
    "moderado":    0.08,   # 8%
    "agresivo":    0.12,   # 12%
}

_MAX_EXP_TOTAL = {
    "conservador": 0.15,   # 15% total simultáneo
    "moderado":    0.25,   # 25%
    "agresivo":    0.40,   # 40%
}

# Factor de descuento por correlación de liga (mismo torneo → reducir exposición)
_CORRELATION_PENALTY = 0.70   # 30% de reducción si hay evento correlacionado activo


# ─── KELLY CRITERION ─────────────────────────────────────────────────────────

def calcular_fraccion_kelly(
    p: float,
    cuota_decimal: float,
    perfil_riesgo: str = "moderado",
) -> float:
    """
    Calcula la fracción óptima de capital a invertir según Kelly fraccionado.

    f* = (b·p − q) / b
    donde:
        b = cuota decimal − 1  (cuota neta)
        p = probabilidad de éxito (estimada por Master AI)
        q = 1 − p

    Args:
        p: probabilidad de éxito [0, 1]
        cuota_decimal: cuota decimal de la casa
        perfil_riesgo: "conservador" | "moderado" | "agresivo"

    Returns:
        fracción del bankroll a invertir [0, cap_máximo]
    """
    if not (0 < p < 1):
        return 0.0

    b = cuota_decimal - 1.0
    if b <= 0:
        return 0.0

    q = 1.0 - p
    kelly_puro = (b * p - q) / b

    if kelly_puro <= 0:
        return 0.0

    divisor = _KELLY_DIVISOR.get(perfil_riesgo, 2)
    kelly_fraccionado = kelly_puro / divisor

    cap = _MAX_EXP_EVENTO.get(perfil_riesgo, 0.08)
    return min(kelly_fraccionado, cap)


# ─── BANKROLL MANAGER ────────────────────────────────────────────────────────

@dataclass
class SenalyKelly:
    ticker: str
    resultado_rec: str            # "local" | "empate" | "visitante"
    prob_ia: float
    cuota: float
    ev: float
    kelly_fraccion: float
    monto_pct: float
    monto_moneda: float
    saldo_disponible: float
    alerta: str = ""              # advertencia al usuario si procede


@dataclass
class BankrollSettings:
    saldo_declarado: float
    perfil_riesgo: str = "moderado"
    kelly_divisor: float = 2.0
    max_exp_evento: float = 0.08
    max_exp_total: float = 0.25
    max_eventos_simult: int = 5
    ajuste_correlacion: bool = True
    exposicion_actual: float = 0.0   # fracción del saldo ya comprometida


def bankroll_manager(
    ticker: str,
    resultado_rec: str,
    prob_ia: float,
    cuota: float,
    ev: float,
    settings: BankrollSettings,
    eventos_activos_misma_liga: int = 0,
) -> SenalyKelly:
    """
    Convierte la señal del Master AI en una instrucción operativa completa.

    Aplica:
        1. Kelly fraccionado según perfil
        2. Cap por evento
        3. Cap de exposición total
        4. Penalización por correlación de liga
        5. Validación de slots disponibles
    """
    kelly_bruto = calcular_fraccion_kelly(prob_ia, cuota, settings.perfil_riesgo)

    # Ajuste por correlación de liga (Brecha A — sección 3)
    if settings.ajuste_correlacion and eventos_activos_misma_liga > 0:
        kelly_bruto *= _CORRELATION_PENALTY ** eventos_activos_misma_liga

    # Cap de exposición total restante
    disponible_total = max(0.0, settings.max_exp_total - settings.exposicion_actual)
    kelly_final = min(kelly_bruto, disponible_total)

    # Verificar slots disponibles
    alerta = ""
    if settings.exposicion_actual >= settings.max_exp_total:
        alerta = "EXPOSICIÓN_MÁXIMA_ALCANZADA"
        kelly_final = 0.0

    monto_moneda = kelly_final * settings.saldo_declarado
    saldo_disp   = settings.saldo_declarado * (1 - settings.exposicion_actual)

    return SenalyKelly(
        ticker=ticker,
        resultado_rec=resultado_rec,
        prob_ia=prob_ia,
        cuota=cuota,
        ev=ev,
        kelly_fraccion=round(kelly_final, 4),
        monto_pct=round(kelly_final * 100, 2),
        monto_moneda=round(monto_moneda, 2),
        saldo_disponible=round(saldo_disp, 2),
        alerta=alerta,
    )


# ─── TRADING OUT — BRECHA B ──────────────────────────────────────────────────

@dataclass
class TradingOutResult:
    stake_lay_sugerido: float
    ganancia_si_ocurre: float
    ganancia_si_no_ocurre: float
    ganancia_garantizada: float     # mín de ambos escenarios
    es_rentable: bool
    descripcion: str


def calcular_trading_out(
    stake_back: float,
    cuota_back_entrada: float,
    cuota_lay_actual: float,
    comision_exchange: float = 0.05,
) -> TradingOutResult:
    """
    Determina el stake lay que iguala la ganancia en ambos resultados posibles,
    neutralizando la posición y asegurando profit (o limitando pérdida).

    Fórmula:
        stake_lay = (stake_back × cuota_back) / cuota_lay_actual

        ganancia_si_ocurre   = stake_back × (cuota_back − 1) − stake_lay × (cuota_lay_actual − 1)
        ganancia_si_no_ocurre = stake_lay × (1 − comision) − stake_back

    Args:
        stake_back:            importe apostado en back (a favor)
        cuota_back_entrada:    cuota al entrar en la posición back
        cuota_lay_actual:      cuota lay disponible ahora en el exchange
        comision_exchange:     comisión del exchange sobre ganancias lay (default 5%)
    """
    if cuota_lay_actual <= 1:
        return TradingOutResult(0, 0, 0, 0, False, "Cuota lay inválida")

    stake_lay = (stake_back * cuota_back_entrada) / cuota_lay_actual

    ganancia_si_ocurre    = (stake_back * (cuota_back_entrada - 1)) \
                            - (stake_lay * (cuota_lay_actual - 1))
    ganancia_si_no_ocurre = (stake_lay - stake_lay * comision_exchange) - stake_back

    garantizada = min(ganancia_si_ocurre, ganancia_si_no_ocurre)
    es_rentable  = garantizada > 0

    if es_rentable:
        desc = f"Lay {stake_lay:.2f} → profit garantizado {garantizada:.2f}"
    elif ganancia_si_ocurre > 0 or ganancia_si_no_ocurre > 0:
        desc = f"Lay {stake_lay:.2f} → reduce pérdida máxima a {abs(garantizada):.2f}"
    else:
        desc = "Sin ventana de trading-out rentable en este momento"

    return TradingOutResult(
        stake_lay_sugerido=round(stake_lay, 2),
        ganancia_si_ocurre=round(ganancia_si_ocurre, 2),
        ganancia_si_no_ocurre=round(ganancia_si_no_ocurre, 2),
        ganancia_garantizada=round(garantizada, 2),
        es_rentable=es_rentable,
        descripcion=desc,
    )


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def responsabilidad_lay(stake_lay: float, cuota_lay: float) -> float:
    """Capital bloqueado en una posición lay: stake × (cuota − 1)."""
    return round(stake_lay * (cuota_lay - 1), 2)


def ganancia_potencial_back(stake: float, cuota: float) -> float:
    """Ganancia neta de una posición back si acierta: stake × (cuota − 1)."""
    return round(stake * (cuota - 1), 2)


def roi_esperado(ev: float, kelly_fraccion: float, n_apuestas: int = 100) -> float:
    """ROI compuesto esperado tras n apuestas con EV y Kelly dados."""
    if kelly_fraccion <= 0 or ev <= 0:
        return 0.0
    tasa_crecimiento = 1 + ev * kelly_fraccion
    return round((tasa_crecimiento ** n_apuestas - 1) * 100, 2)
