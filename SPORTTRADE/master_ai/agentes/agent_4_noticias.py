"""
Agente 4 — Noticias y Sentimiento.
Analiza el sentimiento de noticias recientes sobre ambos equipos.
Usa puntuación de sentimiento (-1 a +1) para ajustar probabilidades.
En producción: conectar con NLP sobre feeds de noticias deportivas.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class SentimientoEquipo:
    equipo: str
    score_sentimiento: float          # -1 (negativo) a +1 (positivo)
    num_noticias: int = 0
    keywords_positivos: list[str] = field(default_factory=list)   # "remontada", "motivados"
    keywords_negativos: list[str] = field(default_factory=list)   # "crisis", "vestuario roto"
    confianza_fuente: float = 0.7     # 0-1: fiabilidad de la fuente de noticias


_NOTICIAS_KEYWORDS_POSITIVOS = {
    "victoria", "remontada", "forma", "motivados", "récord",
    "confianza", "recuperados", "titular", "refuerzo",
}
_NOTICIAS_KEYWORDS_NEGATIVOS = {
    "crisis", "derrota", "conflicto", "lesión", "sanción",
    "descenso", "presión", "dimisión", "tensión", "deuda",
}


def calcular(sentimiento_local: SentimientoEquipo, sentimiento_visit: SentimientoEquipo) -> dict:
    """
    Ajusta probabilidades según diferencial de sentimiento mediático.
    Un score de +0.5 local vs -0.3 visitante favorece al local.
    """
    # Ponderado por fiabilidad de fuente
    score_l = sentimiento_local.score_sentimiento * sentimiento_local.confianza_fuente
    score_v = sentimiento_visit.score_sentimiento * sentimiento_visit.confianza_fuente

    diferencial = score_l - score_v   # [-2, +2]

    # Ajuste proporcional (máx ±8% de impacto sobre probabilidades base)
    ajuste = diferencial * 0.04

    prob_local     = 0.40 + ajuste
    prob_visitante = 0.32 - ajuste
    prob_empate    = 1.0 - prob_local - prob_visitante

    prob_local     = max(0.05, min(0.85, prob_local))
    prob_visitante = max(0.05, min(0.85, prob_visitante))
    prob_empate    = max(0.05, min(0.70, prob_empate))

    total = prob_local + prob_empate + prob_visitante
    prob_local     /= total
    prob_empate    /= total
    prob_visitante /= total

    # Confianza: baja si hay pocas noticias
    total_noticias = sentimiento_local.num_noticias + sentimiento_visit.num_noticias
    confianza = min(0.75, total_noticias / 20) if total_noticias > 0 else 0.20

    return {
        "agente_id": "agent_4_noticias",
        "prob_local": round(prob_local, 4),
        "prob_empate": round(prob_empate, 4),
        "prob_visitante": round(prob_visitante, 4),
        "confianza": round(confianza, 3),
        "features": {
            "score_sentimiento_local": round(score_l, 3),
            "score_sentimiento_visit": round(score_v, 3),
            "diferencial": round(diferencial, 3),
            "noticias_local": sentimiento_local.num_noticias,
            "noticias_visit": sentimiento_visit.num_noticias,
        },
    }


def analizar_texto(texto: str) -> float:
    """
    Análisis de sentimiento simple basado en keywords.
    En producción: reemplazar con modelo NLP (BERT, Transformers).
    Returns score [-1, +1].
    """
    palabras = set(texto.lower().split())
    positivos = len(palabras & _NOTICIAS_KEYWORDS_POSITIVOS)
    negativos = len(palabras & _NOTICIAS_KEYWORDS_NEGATIVOS)
    total = positivos + negativos
    if total == 0:
        return 0.0
    return round((positivos - negativos) / total, 3)
