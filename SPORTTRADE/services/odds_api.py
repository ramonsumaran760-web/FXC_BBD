"""
odds_api.py — Integración con The Odds API para datos en tiempo real.

The Odds API: https://the-odds-api.com
- Odds en tiempo real de Bet365, Pinnacle, Betfair, DraftKings y 40+ bookmakers
- Cubre FIFA World Cup 2026
- Plan gratuito: 500 requests/mes
- Sin key: usa endpoint de demo (datos limitados)
"""
from __future__ import annotations
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger("fxcbbd.odds_api")

ODDS_BASE = "https://api.the-odds-api.com/v4"
WC_SPORT_KEY = "soccer_fifa_world_cup"


def _get_key() -> str:
    """Lee la clave de env en cada llamada — nunca cachea el valor vacío."""
    return os.getenv("ODDS_API_KEY", "")
INTL_SPORTS   = [
    "soccer_fifa_world_cup",
    "soccer_conmebol_copa_america",
    "soccer_uefa_euro_qualification",
    "soccer_international_friendlies",
]


# ─── HELPER ───────────────────────────────────────────────────────────────────

async def _get(path: str, params: dict) -> dict | list | None:
    key = _get_key()
    if not key:
        logger.warning("ODDS_API_KEY no configurada — sin acceso a The Odds API")
        return None
    params["apiKey"] = key
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{ODDS_BASE}{path}", params=params)
            remaining = r.headers.get("x-requests-remaining", "?")
            logger.info("Odds API — %s | HTTP %s | requests left: %s", path, r.status_code, remaining)
            if r.status_code == 200:
                return r.json()
            elif r.status_code == 401:
                logger.error("ODDS_API_KEY inválida o expirada")
            elif r.status_code == 429:
                logger.error("Límite de requests de The Odds API alcanzado")
            else:
                logger.warning("Odds API error %s: %s", r.status_code, r.text[:200])
    except Exception as e:
        logger.error("Odds API connection error: %s", e)
    return None


# ─── SPORTS DISPONIBLES ───────────────────────────────────────────────────────

async def fetch_active_sports() -> list[dict]:
    """Retorna lista de deportes activos (para verificar que WC está disponible)."""
    result = await _get("/sports", {"all": "false"})
    return result or []


# ─── ODDS + PARTIDOS DEL MUNDIAL ─────────────────────────────────────────────

async def fetch_world_cup_odds(
    regions: str = "eu",
    markets: str = "h2h",
) -> list[dict]:
    """
    Retorna todos los partidos del Mundial 2026 con odds en tiempo real.
    regions: 'eu' (Europa), 'us', 'uk', 'au'
    markets: 'h2h' (1X2), 'spreads', 'totals'
    """
    result = await _get(
        f"/sports/{WC_SPORT_KEY}/odds",
        {
            "regions": regions,
            "markets": markets,
            "dateFormat": "iso",
            "oddsFormat": "decimal",
        },
    )
    return result or []


# ─── SCORES EN VIVO ───────────────────────────────────────────────────────────

async def fetch_world_cup_scores(days_from: int = 1) -> list[dict]:
    """
    Retorna marcadores en vivo y resultados recientes del Mundial.
    days_from: cuántos días atrás incluir resultados (1 = hoy y ayer)
    """
    result = await _get(
        f"/sports/{WC_SPORT_KEY}/scores",
        {"daysFrom": str(days_from), "dateFormat": "iso"},
    )
    return result or []


# ─── MAPEO A FORMATO INTERNO ──────────────────────────────────────────────────

def parse_odds_event(ev: dict, scores_map: dict | None = None) -> dict | None:
    """
    Convierte un evento de The Odds API al formato interno del sistema.

    Retorna:
    {
        id, odds_id, liga, l, v, date, live, done, sc, min,
        bl, be, bv,          # cuotas back local/empate/visita (media del mercado)
        bl_best, bv_best,    # mejor cuota de mercado disponible
        bookmakers,          # lista completa de bookmakers con sus cuotas
    }
    """
    try:
        home = ev["home_team"]
        away = ev["away_team"]
        commence = ev.get("commence_time", "")

        # Abreviaciones simples (3 letras)
        h_abbr = _abbr(home)
        v_abbr = _abbr(away)
        event_id = f"{h_abbr}-{v_abbr}"

        # Scores en vivo
        sc, live, done, score_home, score_away = "", False, False, 0, 0
        if scores_map:
            score_data = scores_map.get(ev.get("id", ""))
            if score_data:
                completed = score_data.get("completed", False)
                live = not completed and score_data.get("scores") is not None
                done = completed
                scores = score_data.get("scores") or []
                for s in scores:
                    if s.get("name") == home:   score_home = int(s.get("score", 0))
                    elif s.get("name") == away: score_away = int(s.get("score", 0))
                if live or done:
                    sc = f"{score_home}-{score_away}"

        # Extraer odds de todos los bookmakers
        bookmakers_data = []
        bl_vals, be_vals, bv_vals = [], [], []

        for bk in ev.get("bookmakers", []):
            for market in bk.get("markets", []):
                if market.get("key") != "h2h":
                    continue
                outcomes = {o["name"]: o["price"] for o in market.get("outcomes", [])}
                bl = outcomes.get(home, 0)
                bv = outcomes.get(away, 0)
                # El empate puede llamarse "Draw" o estar ausente en algunos mercados
                be = outcomes.get("Draw", outcomes.get("draw", 0))
                if bl > 1 and be > 1 and bv > 1:
                    bl_vals.append(bl)
                    be_vals.append(be)
                    bv_vals.append(bv)
                    bookmakers_data.append({
                        "nombre": bk.get("title", bk.get("key", "")),
                        "local":  bl,
                        "empate": be,
                        "visita": bv,
                        "actualizado": market.get("last_update", ""),
                    })

        if not bl_vals:
            return None  # sin cuotas disponibles aún

        # Promedio de mercado (sin margen todavía)
        bl_avg = round(sum(bl_vals) / len(bl_vals), 3)
        be_avg = round(sum(be_vals) / len(be_vals), 3)
        bv_avg = round(sum(bv_vals) / len(bv_vals), 3)

        # Mejor cuota disponible en el mercado
        bl_best = max(bl_vals)
        be_best = max(be_vals)
        bv_best = max(bv_vals)

        return {
            "id":          event_id,
            "odds_id":     ev.get("id", ""),
            "liga":        "FIFA Mundial 2026",
            "l":           home,
            "v":           away,
            "date":        commence,
            "live":        live,
            "done":        done,
            "sc":          sc,
            "min":         0,

            # Cuotas medias del mercado
            "bl":          bl_avg,
            "be":          be_avg,
            "bv":          bv_avg,

            # Mejor cuota disponible (máximo valor al apostar)
            "bl_best":     bl_best,
            "be_best":     be_best,
            "bv_best":     bv_best,

            # Detalle de bookmakers
            "bookmakers":  sorted(bookmakers_data, key=lambda x: -x["local"])[:8],

            # Placeholder para análisis IA (se llena por analyzeMatchWithAI)
            "pl": 0, "pe": 0, "pv": 0,
            "ev": 0, "conf": 0, "kelly": 0,
            "ag": [0,0,0,0,0,0,0,0],
            "xgl": 0, "xgv": 0,
            "_loading": True,
        }
    except Exception as e:
        logger.warning("parse_odds_event error: %s", e)
        return None


def _abbr(team_name: str) -> str:
    """Genera abreviatura de 3 letras del nombre del equipo."""
    words = team_name.upper().split()
    if len(words) == 1:
        return words[0][:3]
    # Países multi-palabra: tomar iniciales o primeras letras
    specials = {
        "UNITED STATES": "USA",
        "ESTADOS UNIDOS": "USA",
        "SOUTH KOREA": "KOR",
        "COREA DEL SUR": "KOR",
        "SAUDI ARABIA": "KSA",
        "COSTA RICA": "CRC",
        "IVORY COAST": "CIV",
        "NEW ZEALAND": "NZL",
        "TRINIDAD AND TOBAGO": "TRI",
    }
    upper = team_name.upper()
    if upper in specials:
        return specials[upper]
    return "".join(w[0] for w in words)[:3]


# ─── ENDPOINT COMPLETO: odds + scores en paralelo ─────────────────────────────

async def fetch_full_world_cup_data() -> list[dict]:
    """
    Fetcha odds + scores en paralelo y los combina.
    Retorna lista de partidos con cuotas reales de bookmakers.
    """
    import asyncio
    odds_list, scores_list = await asyncio.gather(
        fetch_world_cup_odds(),
        fetch_world_cup_scores(days_from=1),
    )

    # Mapa de scores por event ID
    scores_map: dict[str, dict] = {}
    for s in (scores_list or []):
        scores_map[s.get("id", "")] = s

    results = []
    for ev in (odds_list or []):
        parsed = parse_odds_event(ev, scores_map)
        if parsed:
            results.append(parsed)

    # Ordenar: en vivo primero, luego por hora de inicio
    results.sort(key=lambda x: (not x["live"], x["done"], x.get("date", "")))
    return results
