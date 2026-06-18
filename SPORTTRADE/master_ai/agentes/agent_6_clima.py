"""
Agente 6 — Clima y Condiciones del Terreno.
Evalúa cómo el clima afecta el estilo de juego y las probabilidades.
Lluvia/frío favorece equipos físicos y defensivos → más empates.
Calor extremo → fatiga → menos goles en el 2T.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

CondicionClima = Literal["soleado", "nublado", "lluvia_ligera", "lluvia_fuerte", "nieve", "calor_extremo", "viento_fuerte"]


@dataclass
class CondicionesPartido:
    temperatura_c: float
    condicion: CondicionClima
    humedad_pct: float = 50.0
    viento_kmh: float = 0.0
    cesped: Literal["bueno", "regular", "malo"] = "bueno"
    estadio_techado: bool = False


# Impacto del clima en probabilidades (delta sobre base)
_CLIMA_IMPACTO = {
    "soleado":        {"local": 0.00, "empate": 0.00, "visitante": 0.00},
    "nublado":        {"local": 0.00, "empate": 0.01, "visitante": -0.01},
    "lluvia_ligera":  {"local": 0.01, "empate": 0.03, "visitante": -0.04},
    "lluvia_fuerte":  {"local": 0.02, "empate": 0.05, "visitante": -0.07},
    "nieve":          {"local": 0.03, "empate": 0.06, "visitante": -0.09},
    "calor_extremo":  {"local": -0.02, "empate": 0.04, "visitante": -0.02},
    "viento_fuerte":  {"local": 0.01, "empate": 0.03, "visitante": -0.04},
}


def calcular(condiciones: CondicionesPartido) -> dict:
    """
    Ajusta probabilidades por condiciones meteorológicas.
    Estadio techado → clima irrelevante.
    """
    if condiciones.estadio_techado:
        return _output_neutro(motivo="estadio_cubierto")

    impacto = _CLIMA_IMPACTO.get(condiciones.condicion, {"local": 0, "empate": 0, "visitante": 0})

    # Temperaturas extremas → aumentan empates (fatiga, menor ritmo)
    if condiciones.temperatura_c < 5:
        impacto = {k: v + 0.01 * (k == "empate") for k, v in impacto.items()}
    elif condiciones.temperatura_c > 30:
        impacto["empate"] += 0.02

    # Viento fuerte → aero-balístico → impacto adicional
    if condiciones.viento_kmh > 40:
        impacto["empate"] += 0.03
        impacto["local"]  += 0.01
        impacto["visitante"] -= 0.04

    # Césped malo → juego interrumpido → más errores → más goles en contra del favorito
    if condiciones.cesped == "malo":
        impacto["empate"] += 0.02

    prob_local     = max(0.05, 0.40 + impacto["local"])
    prob_empate    = max(0.05, 0.28 + impacto["empate"])
    prob_visitante = max(0.05, 0.32 + impacto["visitante"])

    total = prob_local + prob_empate + prob_visitante
    prob_local     /= total
    prob_empate    /= total
    prob_visitante /= total

    # Confianza: menor si el clima es extremo (más incertidumbre)
    confianza = 0.60 if condiciones.condicion in ("lluvia_fuerte", "nieve", "calor_extremo") else 0.72

    return {
        "agente_id": "agent_6_clima",
        "prob_local": round(prob_local, 4),
        "prob_empate": round(prob_empate, 4),
        "prob_visitante": round(prob_visitante, 4),
        "confianza": confianza,
        "features": {
            "temperatura_c": condiciones.temperatura_c,
            "condicion": condiciones.condicion,
            "viento_kmh": condiciones.viento_kmh,
            "cesped": condiciones.cesped,
            "impacto_aplicado": impacto,
        },
    }


def _output_neutro(motivo: str = "") -> dict:
    return {
        "agente_id": "agent_6_clima",
        "prob_local": 0.40,
        "prob_empate": 0.28,
        "prob_visitante": 0.32,
        "confianza": 0.50,
        "features": {"motivo": motivo},
    }
