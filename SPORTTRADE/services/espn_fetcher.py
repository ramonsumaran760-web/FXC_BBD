"""
espn_fetcher.py — Servicio de datos ESPN para fútbol en vivo (todas las competiciones).
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

# (slug, nombre_display) — ordenadas por prioridad
# El slug del Mundial va primero; si devuelve datos se usa como fuente principal.
# Las demás ligas se intentan en paralelo para mostrar todos los partidos del día.
_COMPETITIONS: list[tuple[str, str]] = [
    # ── FIFA World Cup 2026 ───────────────────────────────────────────
    ("fifa.world",             "FIFA Mundial 2026"),
    ("worldcup",               "FIFA Mundial 2026"),
    ("fifa.worldcup",          "FIFA Mundial 2026"),
    ("fifa.world.2026",        "FIFA Mundial 2026"),
    # ── UEFA ──────────────────────────────────────────────────────────
    ("uefa.champions",         "Champions League"),
    ("uefa.europa",            "Europa League"),
    ("uefa.nations",           "UEFA Nations League"),
    ("uefa.euro",              "Eurocopa"),
    # ── Ligas Europa ──────────────────────────────────────────────────
    ("eng.1",                  "Premier League"),
    ("esp.1",                  "La Liga"),
    ("ger.1",                  "Bundesliga"),
    ("ita.1",                  "Serie A"),
    ("fra.1",                  "Ligue 1"),
    ("por.1",                  "Primeira Liga"),
    ("ned.1",                  "Eredivisie"),
    ("tur.1",                  "Süper Lig"),
    ("sco.1",                  "Scottish Premiership"),
    # ── Américas ──────────────────────────────────────────────────────
    ("usa.1",                  "MLS"),
    ("mex.1",                  "Liga MX"),
    ("arg.1",                  "Liga Profesional Argentina"),
    ("bra.1",                  "Brasileirao"),
    ("col.1",                  "Liga BetPlay Colombia"),
    ("chi.1",                  "Primera División Chile"),
    ("conmebol.copa.america",  "Copa América"),
    ("conmebol.libertadores",  "Copa Libertadores"),
    ("conmebol.sudamericana",  "Copa Sudamericana"),
    ("concacaf.gold",          "Gold Cup CONCACAF"),
    ("concacaf.champions",     "Concacaf Champions Cup"),
    # ── Asia / África ─────────────────────────────────────────────────
    ("afc.asian.qual",         "Clasificatorias AFC"),
    ("caf.nations",            "Copa Africana de Naciones"),
]

# Subset: solo slugs del Mundial (para compatibilidad con funciones legacy)
_ESPN_WC_SLUGS = [slug for slug, name in _COMPETITIONS if "Mundial" in name]


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


# ─── SCOREBOARD (todas las competiciones, partidos en vivo + del día) ────────

async def fetch_scoreboard(date: Optional[str] = None) -> list[dict]:
    """
    Retorna partidos EN VIVO y del día de TODAS las competiciones configuradas.

    Estrategia:
    1. Busca slugs del Mundial (con fallback de fechas para cubrir lag de ESPN).
    2. Busca otras ligas EN PARALELO (solo fecha actual → más rápido).
    3. Desduplicación global por ID de evento ESPN.
    4. Cada evento lleva `_league_name` con el nombre de su competición.
    """
    now_utc = datetime.now(timezone.utc)
    today   = date or now_utc.strftime("%Y%m%d")
    ayer    = (now_utc - timedelta(days=1)).strftime("%Y%m%d")

    seen_ids:    set[str]   = set()
    all_events:  list[dict] = []

    # ── Paso 1: Mundial — 3 estrategias de fecha por si ESPN tiene lag ────────
    wc_slugs = [(s, n) for s, n in _COMPETITIONS if "Mundial" in n]
    wc_found = False
    for slug, league_name in wc_slugs:
        if wc_found:
            break
        for params in [{}, {"dates": today, "limit": "50"}, {"dates": ayer, "limit": "50"}]:
            p = {**params, "limit": "50"}
            d = await _get(f"{ESPN_BASE}/{slug}/scoreboard", p)
            new = 0
            for ev in _extract_events(d):
                eid = str(ev.get("id", ""))
                if eid and eid not in seen_ids:
                    seen_ids.add(eid)
                    ev["_league_name"] = league_name
                    all_events.append(ev)
                    new += 1
            if new:
                logger.info("ESPN WC: +%d eventos slug='%s'", new, slug)
                wc_found = True
                break  # slug encontrado — no probar más fechas para este slug

    # ── Paso 2: Resto de competiciones — fetch en paralelo ────────────────────
    other_comps = [(s, n) for s, n in _COMPETITIONS if "Mundial" not in n]

    async def _fetch_other(slug: str, league_name: str) -> list[dict]:
        results: list[dict] = []
        try:
            for params in [{}, {"dates": today, "limit": "30"}]:
                p = {**params, "limit": "30"}
                d = await _get(f"{ESPN_BASE}/{slug}/scoreboard", p)
                new = 0
                for ev in _extract_events(d):
                    eid = str(ev.get("id", ""))
                    if eid and eid not in seen_ids:
                        seen_ids.add(eid)
                        ev["_league_name"] = league_name
                        results.append(ev)
                        new += 1
                if new:
                    logger.info("ESPN other: +%d eventos liga='%s'", new, league_name)
                    break
        except Exception as exc:
            logger.debug("ESPN fetch error slug=%s: %s", slug, exc)
        return results

    other_batches = await asyncio.gather(*[_fetch_other(s, n) for s, n in other_comps])
    for batch in other_batches:
        all_events.extend(batch)

    live_count = sum(
        1 for ev in all_events
        if ev.get("status", {}).get("type", {}).get("state") == "in"
    )
    logger.info(
        "ESPN scoreboard total: %d eventos (%d en vivo) de %d competiciones",
        len(all_events), live_count,
        len({ev.get("_league_name") for ev in all_events}),
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
