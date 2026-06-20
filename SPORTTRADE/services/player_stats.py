"""
player_stats.py — Estadísticas en tiempo real de jugadores vía ESPN.
Métricas: toques acertados/errados, km estimados, asistencias, balance, lesiones.
"""
from __future__ import annotations
import asyncio
import hashlib
import logging
from typing import Optional

import httpx

logger = logging.getLogger("fxcbbd.players")

ESPN_BASE    = "https://site.api.espn.com/apis/site/v2/sports/soccer"
ESPN_TIMEOUT = 12.0

# ── Km base por posición (partido completo 90 min) ───────────────────────────
_KM_BASE: dict[str, float] = {
    "GK": 5.8,  "G": 5.8,
    "CB": 9.5,  "SW": 9.5, "DC": 9.5,
    "LB": 11.0, "RB": 11.0, "LWB": 11.8, "RWB": 11.8, "WB": 11.4,
    "DM": 11.5, "CDM": 11.5, "DLP": 11.5,
    "CM": 12.5, "MC": 12.5, "BOX": 12.8, "M": 12.0,
    "CAM": 11.2, "AM": 11.2, "SS": 11.0,
    "LM": 11.0, "RM": 11.0,
    "LW": 10.5, "RW": 10.5, "WG": 10.5, "W": 10.5,
    "CF": 10.0, "FW": 10.0, "ST": 10.0, "F": 10.0, "ATT": 10.0,
}

# ── Liga display → slug ESPN ──────────────────────────────────────────────────
_LIGA_SLUG: dict[str, str] = {
    "FIFA Mundial 2026":           "fifa.world",
    "Champions League":            "uefa.champions",
    "Europa League":               "uefa.europa",
    "UEFA Nations League":         "uefa.nations",
    "Eurocopa":                    "uefa.euro",
    "Premier League":              "eng.1",
    "La Liga":                     "esp.1",
    "Bundesliga":                  "ger.1",
    "Serie A":                     "ita.1",
    "Ligue 1":                     "fra.1",
    "Primeira Liga":               "por.1",
    "Eredivisie":                  "ned.1",
    "MLS":                         "usa.1",
    "Liga MX":                     "mex.1",
    "Brasileirao":                 "bra.1",
    "Liga Profesional Argentina":  "arg.1",
    "Copa Libertadores":           "conmebol.libertadores",
    "Copa Sudamericana":           "conmebol.sudamericana",
    "Copa América":                "conmebol.copa.america",
    "Gold Cup CONCACAF":           "concacaf.gold",
}
_FALLBACK_SLUGS = ["fifa.world", "worldcup", "uefa.champions", "eng.1",
                   "esp.1", "ger.1", "ita.1", "fra.1", "usa.1", "mex.1",
                   "bra.1", "arg.1", "conmebol.libertadores", "conmebol.copa.america"]


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_summary(slug: str, event_id: str) -> dict:
    url = f"{ESPN_BASE}/{slug}/summary"
    try:
        async with httpx.AsyncClient(timeout=ESPN_TIMEOUT) as c:
            r = await c.get(url, params={"event": event_id})
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        logger.debug("ESPN summary slug=%s event=%s: %s", slug, event_id, e)
    return {}


def _km_estimate(pos: str, match_min: int, name: str) -> float:
    base    = _KM_BASE.get(pos.upper(), 10.5)
    frac    = max(0.0, min(1.0, match_min / 90))
    noise   = ((int(hashlib.md5(name.encode()).hexdigest()[:4], 16) % 100) - 50) / 600
    return round(base * frac + noise, 2)


def _safe_float(val) -> float:
    try:
        return float(str(val).replace("%", "").strip())
    except Exception:
        return 0.0


def _stat_from_row(names: list, raw: list, *keys) -> float:
    for key in keys:
        if key in names:
            i = names.index(key)
            if i < len(raw):
                return _safe_float(raw[i])
    return 0.0


def _parse_players(boxscore_players: list[dict], match_min: int) -> list[dict]:
    teams_out = []
    for team_block in boxscore_players:
        team_name   = team_block.get("team", {}).get("displayName", "?")
        team_id     = team_block.get("team", {}).get("id", "")
        home_away   = team_block.get("homeAway", "home")
        stats_groups= team_block.get("statistics", [])
        if not stats_groups:
            continue

        group   = stats_groups[0]
        names   = group.get("names", [])
        athletes= group.get("athletes", [])

        players = []
        for entry in athletes:
            ath     = entry.get("athlete", {})
            pos     = ath.get("position", {}).get("abbreviation", "CM")
            jersey  = ath.get("jersey", "?")
            name    = ath.get("displayName", "Desconocido")
            starter = bool(entry.get("starter", False))
            active  = bool(entry.get("active", True))
            raw     = entry.get("stats", [])

            def s(*keys): return _stat_from_row(names, raw, *keys)

            # ── Stats ESPN (múltiples alias por liga) ─────────────────────────
            pa   = s("PA",  "passesMade",       "passesAttempted")
            pc   = s("PC",  "passesComplete",    "passesCompleted")
            goles  = s("G",   "goals")
            asist  = s("A",   "assists")
            sh     = s("SH",  "totalShots",       "shots")
            shg    = s("SHG", "shotsOnTarget",    "shotsOnGoal")
            fls    = s("FLS", "fouls",            "foulsConceded")
            yc     = s("YC",  "yellowCards",      "bookings")
            rc     = s("RC",  "redCards")
            blk    = s("BLK", "blocks")
            inter  = s("INT", "interceptions")
            tac    = s("TKL", "tackles",          "tacklesWon")
            min_p  = s("MIN", "minutesPlayed")
            if min_p == 0:
                min_p = float(match_min) if starter else 0.0

            # ── Toques ────────────────────────────────────────────────────────
            # ESPN no siempre da "touches" explícito — estimamos desde acciones
            toques_raw   = s("TOT", "touches", "totalTouches")
            if toques_raw == 0:
                toques_raw = pa + sh + blk + inter + tac + max(1, int(pa * 0.12))
            toques_ok    = int(pc + shg + blk + inter + tac)
            toques_err   = max(0, int(toques_raw) - toques_ok)
            precision    = round(toques_ok / max(1, toques_raw) * 100, 1)

            km = _km_estimate(pos, int(min_p) or match_min, name)

            # ── Balance individual (0–100) ─────────────────────────────────
            balance = (
                precision * 0.40
                + goles  * 15
                + asist  * 10
                + shg    * 4
                + blk    * 3
                + inter  * 2
                + tac    * 2
                - fls    * 3
                - yc     * 8
                - rc     * 25
                - toques_err * 0.5
            )
            balance = round(max(0.0, min(100.0, balance)), 1)

            # ── Radar (5 ejes normalizados 0–100) ─────────────────────────
            radar = {
                "precision":  precision,
                "km":         round(min(100, km / 13 * 100), 1),
                "ofensiva":   round(min(100, goles*15 + asist*10 + shg*4), 1),
                "defensiva":  round(min(100, blk*8  + inter*6  + tac*5), 1),
                "disciplina": round(max(0, 100 - fls*5 - yc*15 - rc*40), 1),
            }

            players.append({
                "name":       name,
                "jersey":     jersey,
                "pos":        pos,
                "starter":    starter,
                "active":     active,
                "min":        int(min_p),
                "toques":     int(toques_raw),
                "toques_ok":  toques_ok,
                "toques_err": toques_err,
                "precision":  precision,
                "km":         km,
                "goles":      int(goles),
                "asist":      int(asist),
                "tiros":      int(sh),
                "tiros_ok":   int(shg),
                "faltas":     int(fls),
                "amarillas":  int(yc),
                "rojas":      int(rc),
                "bloqueos":   int(blk),
                "interc":     int(inter),
                "tackeos":    int(tac),
                "lesionado":  not active and starter,
                "balance":    balance,
                "radar":      radar,
            })

        if not players:
            continue

        starters = [p for p in players if p["starter"]]
        subs     = [p for p in players if not p["starter"]]

        # ── Balance del equipo ────────────────────────────────────────────
        team_km        = round(sum(p["km"]       for p in starters), 1)
        team_toques    = sum(p["toques"]          for p in starters)
        team_toques_ok = sum(p["toques_ok"]       for p in starters)
        team_precision = round(team_toques_ok / max(1, team_toques) * 100, 1)
        team_goles     = sum(p["goles"]           for p in starters)
        team_asist     = sum(p["asist"]           for p in starters)
        team_faltas    = sum(p["faltas"]           for p in starters)
        team_balance   = round(sum(p["balance"]   for p in starters) / max(1, len(starters)), 1)
        team_radar     = {
            k: round(sum(p["radar"][k] for p in starters) / max(1, len(starters)), 1)
            for k in ["precision", "km", "ofensiva", "defensiva", "disciplina"]
        }
        lesionados = [p["name"] for p in players if p["lesionado"]]

        teams_out.append({
            "team":           team_name,
            "team_id":        team_id,
            "home_away":      home_away,
            "players":        players,
            "starters":       starters,
            "subs":           subs,
            "team_km":        team_km,
            "team_toques":    team_toques,
            "team_precision": team_precision,
            "team_goles":     team_goles,
            "team_asist":     team_asist,
            "team_faltas":    team_faltas,
            "team_balance":   team_balance,
            "team_radar":     team_radar,
            "lesionados":     lesionados,
        })

    return teams_out


# ── Función principal ─────────────────────────────────────────────────────────

async def fetch_player_stats(
    event_id: str,
    liga: Optional[str] = None,
    match_min: int = 45,
    home: Optional[str] = None,
    away: Optional[str] = None,
) -> dict:
    """
    Obtiene y procesa estadísticas de jugadores de un partido ESPN.

    Args:
        event_id:  ID del evento ESPN (campo odds_id del match en el frontend)
        liga:      Nombre de la liga para elegir el slug correcto
        match_min: Minuto actual del partido (para estimar km)
        home:      Nombre del equipo local (para búsqueda en SofaScore)
        away:      Nombre del equipo visitante (para búsqueda en SofaScore)

    Returns:
        dict con teams[], match_min, event_id, clock, state, source
    """
    # ── Fuente 1: SofaScore (datos reales — ratings, pases, tackles, etc.) ────
    if home and away:
        try:
            from services.sofascore_fetcher import fetch_sofascore_players
            sofa = await fetch_sofascore_players(home, away, match_min)
            if sofa.get("teams"):
                sofa["event_id"]  = event_id
                sofa["match_min"] = match_min
                return sofa
            logger.info("SofaScore sin datos, probando ESPN: %s", sofa.get("error", ""))
        except Exception as e:
            logger.warning("SofaScore error: %s", e)

    # ── Fuente 2: ESPN boxscore (fallback) ────────────────────────────────────
    if not event_id:
        return {"error": "Sin event_id y SofaScore no encontró el partido", "teams": []}

    slugs: list[str] = []
    if liga and liga in _LIGA_SLUG:
        slugs.append(_LIGA_SLUG[liga])
    slugs.extend(s for s in _FALLBACK_SLUGS if s not in slugs)

    raw = {}
    used_slug = ""
    for slug in slugs[:8]:
        raw = await _get_summary(slug, event_id)
        if raw.get("boxscore", {}).get("players"):
            used_slug = slug
            logger.info("Jugadores ESPN OK: slug=%s event=%s", slug, event_id)
            break

    bp = raw.get("boxscore", {}).get("players", [])
    if not bp:
        return {
            "error":    "Sin datos de jugadores en SofaScore ni ESPN para este partido. "
                        "Intenta cuando el partido lleve al menos 10 minutos en curso.",
            "teams":    [],
            "event_id": event_id,
        }

    header_comp = (raw.get("header", {}).get("competitions") or [{}])[0]
    status      = header_comp.get("status", {})
    state       = status.get("type", {}).get("state", "")
    clock       = status.get("displayClock", f"{match_min}'")

    teams = _parse_players(bp, match_min)

    # Marcar source para que el frontend sepa qué mostrar
    for t in teams:
        t["source"] = "espn"

    return {
        "event_id":  event_id,
        "source":    "espn",
        "slug":      used_slug,
        "state":     state,
        "clock":     clock,
        "match_min": match_min,
        "teams":     teams,
    }
