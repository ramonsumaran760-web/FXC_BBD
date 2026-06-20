"""
espn_fetcher.py — Servicio de datos ESPN para el Mundial 2026.
Fetcha sin API key usando los endpoints públicos de ESPN.
"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx

logger = logging.getLogger("fxcbbd.espn")

ESPN_BASE    = "https://site.api.espn.com/apis/site/v2/sports/soccer"
ESPN_WC      = f"{ESPN_BASE}/fifa.world"
ESPN_TIMEOUT = 10.0

# Slugs del Mundial 2026 — ESPN puede cambiar el slug en cualquier momento
_ESPN_WC_SLUGS = [
    "fifa.world",
    "worldcup",
    "fifa.worldcup",
    "soccer_fifa_world_cup",
    "fifa.world.2026",
]


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


def _extract_events(d: dict) -> list[dict]:
    """Extrae la lista de eventos de la respuesta ESPN (varios formatos posibles)."""
    events = d.get("events") or []
    if events:
        return events
    # Algunos endpoints anidan por leagues
    for lg in d.get("leagues", []):
        ev = lg.get("events", [])
        if ev:
            return ev
    # O por sports
    for sp in d.get("sports", []):
        for lg in sp.get("leagues", []):
            ev = lg.get("events", [])
            if ev:
                return ev
    return []


# ─── SCOREBOARD (partidos en vivo + del día) ──────────────────────────────────

async def fetch_scoreboard(date: Optional[str] = None) -> list[dict]:
    """
    Retorna lista de eventos del Mundial 2026 — cubre:
    • Partidos en vivo ahora mismo (sin parámetro de fecha → ESPN devuelve live)
    • Partidos del día de hoy UTC
    • Partidos del día de ayer UTC (partidos nocturnos en zonas horarias americanas)

    Desduplicados por ID de evento ESPN.
    """
    now_utc = datetime.now(timezone.utc)
    today   = date or now_utc.strftime("%Y%m%d")
    ayer    = (now_utc - timedelta(days=1)).strftime("%Y%m%d")

    seen_ids:   set[str]  = set()
    all_events: list[dict] = []

    # Estrategias de fetch en orden de prioridad:
    # 1) Sin fecha    → ESPN retorna partidos en vivo / más recientes
    # 2) Fecha hoy    → todos los partidos programados para hoy
    # 3) Fecha ayer   → partidos que pueden seguir en vivo desde ayer (zonas horarias)
    fetch_params = [
        {},                          # live / sin filtro de fecha
        {"dates": today, "limit": "50"},
        {"dates": ayer,  "limit": "50"},
    ]

    for slug in _ESPN_WC_SLUGS:
        url = f"{ESPN_BASE}/{slug}/scoreboard"
        slug_found = False

        for params in fetch_params:
            p = dict(params)
            p.setdefault("limit", "50")
            d = await _get(url, p)
            events = _extract_events(d)

            new_count = 0
            for ev in events:
                eid = str(ev.get("id", ""))
                if eid and eid not in seen_ids:
                    seen_ids.add(eid)
                    all_events.append(ev)
                    new_count += 1

            if new_count:
                slug_found = True
                logger.info(
                    "ESPN scoreboard: +%d eventos slug='%s' params=%s",
                    new_count, slug, p,
                )

        if slug_found:
            # Con el primer slug que devuelve eventos dejamos de probar otros
            break

    live_count = sum(
        1 for ev in all_events
        if ev.get("status", {}).get("type", {}).get("state") == "in"
    )
    logger.info(
        "ESPN scoreboard total: %d eventos (%d en vivo)",
        len(all_events), live_count,
    )
    return all_events


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
