"""
espn_fetcher.py — Servicio de datos ESPN para el Mundial 2026.
Fetcha sin API key usando los endpoints públicos de ESPN.
"""
from __future__ import annotations
import asyncio
import logging
from typing import Optional

import httpx

logger = logging.getLogger("fxcbbd.espn")

ESPN_BASE    = "https://site.api.espn.com/apis/site/v2/sports/soccer"
ESPN_WC      = f"{ESPN_BASE}/fifa.world"   # used by standings/summary/teams
ESPN_TIMEOUT = 8.0

# Slugs a probar en orden — WC 2026 puede usar distinto slug según ESPN
_ESPN_WC_SLUGS = ["fifa.world", "worldcup", "fifa.worldcup", "soccer_fifa_world_cup"]


# ─── CLIENTE COMPARTIDO ───────────────────────────────────────────────────────

async def _get(url: str, params: dict | None = None) -> dict:
    try:
        async with httpx.AsyncClient(timeout=ESPN_TIMEOUT) as c:
            r = await c.get(url, params=params or {})
            if r.status_code == 200:
                return r.json()
            logger.warning("ESPN HTTP %s for %s", r.status_code, url)
    except Exception as e:
        logger.warning("ESPN fetch error %s: %s", url, e)
    return {}


# ─── SCOREBOARD (partidos del día) ────────────────────────────────────────────

async def fetch_scoreboard(date: Optional[str] = None) -> list[dict]:
    """
    Retorna lista de eventos del día probando múltiples slugs ESPN para WC 2026.
    date: 'YYYYMMDD' (opcional, default = hoy UTC)
    """
    from datetime import datetime, timezone
    today = date or datetime.now(timezone.utc).strftime("%Y%m%d")
    params = {"dates": today, "limit": "50"}

    for slug in _ESPN_WC_SLUGS:
        url = f"{ESPN_BASE}/{slug}/scoreboard"
        d = await _get(url, params)
        events = d.get("events") or []
        # ESPN a veces anida eventos dentro de leagues
        if not events:
            for lg in d.get("leagues", []):
                events = lg.get("events", [])
                if events:
                    break
        if events:
            logger.info("ESPN scoreboard: %d eventos via slug '%s' fecha %s", len(events), slug, today)
            return events

    logger.warning("ESPN scoreboard: sin eventos para fecha %s", today)
    return []


# ─── STANDINGS (tabla del Mundial por grupo) ──────────────────────────────────

async def fetch_standings() -> dict[str, dict]:
    """
    Retorna {NOMBRE_EQUIPO_UPPER: {pj,pg,pe,pp,gf,gc,pts,grupo}} desde ESPN.
    """
    d = await _get(f"{ESPN_WC}/standings")
    result: dict[str, dict] = {}

    def sv(stats: list, name: str, default: float = 0.0) -> float:
        for s in stats:
            if s.get("name") == name or s.get("abbreviation") == name:
                try:
                    return float(str(s.get("value", default)).replace("%", ""))
                except (ValueError, TypeError):
                    return default
        return default

    for group in d.get("standings", {}).get("groups", []):
        group_name = group.get("name", "Grupo")
        for entry in group.get("standings", {}).get("entries", []):
            team = entry.get("team", {})
            name = team.get("displayName", "").upper()
            team_id = team.get("id", "")
            if not name:
                continue
            st = entry.get("stats", [])
            result[name] = {
                "team_id":   team_id,
                "abrev":     team.get("abbreviation", name[:3]),
                "pj":        int(sv(st, "gamesPlayed",    3)),
                "pg":        int(sv(st, "wins",           1)),
                "pe":        int(sv(st, "ties",           1)),
                "pp":        int(sv(st, "losses",         1)),
                "gf":        int(sv(st, "pointsFor",      2)),
                "gc":        int(sv(st, "pointsAgainst",  2)),
                "pts":       int(sv(st, "points",         4)),
                "grupo":     group_name,
            }
    return result


# ─── EVENT SUMMARY (stats en vivo / finales) ──────────────────────────────────

async def fetch_event_summary(event_id: str) -> dict:
    """
    Retorna resumen detallado de un partido:
    posesión, tiros, tiros a puerta, córners, faltas, tarjetas.
    """
    d = await _get(f"{ESPN_WC}/summary", {"event": event_id})

    # Extraer equipos del header
    comp = (d.get("header", {}).get("competitions") or [{}])[0]
    competitors = comp.get("competitors", [])
    home_c = next((x for x in competitors if x.get("homeAway") == "home"), {})
    away_c = next((x for x in competitors if x.get("homeAway") == "away"), {})

    def extract_stats(ts: dict) -> dict:
        out = {}
        for s in ts.get("statistics", []):
            key = s.get("name", "")
            raw = str(s.get("displayValue", "0")).replace("%", "").strip()
            try:
                out[key] = float(raw)
            except ValueError:
                out[key] = 0.0
        return out

    home_stats: dict[str, float] = {}
    away_stats: dict[str, float] = {}
    for ts in d.get("boxscore", {}).get("teams", []):
        if ts.get("homeAway") == "home":
            home_stats = extract_stats(ts)
        else:
            away_stats = extract_stats(ts)

    # Línea de goles
    scoring = []
    for play in d.get("keyEvents", []):
        scoring.append({
            "minuto":  play.get("clock", {}).get("displayValue", ""),
            "equipo":  play.get("team", {}).get("displayName", ""),
            "jugador": play.get("athletes", [{}])[0].get("athlete", {}).get("displayName", ""),
            "tipo":    play.get("type", {}).get("text", ""),
        })

    status = comp.get("status", {})
    return {
        "event_id":   event_id,
        "home_team":  home_c.get("team", {}).get("displayName", ""),
        "away_team":  away_c.get("team", {}).get("displayName", ""),
        "home_id":    home_c.get("team", {}).get("id", ""),
        "away_id":    away_c.get("team", {}).get("id", ""),
        "home_score": int(home_c.get("score", 0) or 0),
        "away_score": int(away_c.get("score", 0) or 0),
        "status":     status.get("type", {}).get("state", "pre"),
        "minuto":     status.get("displayClock", "0'"),
        "home_stats": home_stats,
        "away_stats": away_stats,
        "scoring":    scoring,
    }


# ─── TEAM SCHEDULE (últimos partidos del torneo) ──────────────────────────────

async def fetch_team_schedule(team_id: str, limit: int = 5) -> list[dict]:
    """
    Retorna los últimos `limit` partidos jugados por un equipo en el Mundial.
    """
    d = await _get(f"{ESPN_WC}/teams/{team_id}/schedule")
    events = d.get("events", [])

    played = []
    for ev in events:
        status = ev.get("competitions", [{}])[0].get("status", {})
        if status.get("type", {}).get("state") == "post":
            comp = ev.get("competitions", [{}])[0]
            comps = comp.get("competitors", [])
            home_c = next((x for x in comps if x.get("homeAway") == "home"), {})
            away_c = next((x for x in comps if x.get("homeAway") == "away"), {})
            played.append({
                "fecha":    ev.get("date", ""),
                "local":    home_c.get("team", {}).get("displayName", ""),
                "visita":   away_c.get("team", {}).get("displayName", ""),
                "goles_l":  int(home_c.get("score", 0) or 0),
                "goles_v":  int(away_c.get("score", 0) or 0),
                "winner":   (home_c if home_c.get("winner") else away_c).get("team", {}).get("displayName", ""),
            })

    return played[-limit:]
