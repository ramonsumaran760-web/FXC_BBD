"""
sofascore_fetcher.py — Estadísticas reales de jugadores vía SofaScore.
SofaScore tiene ratings de jugadores (0-10), alineaciones y stats en vivo.
Los km recorridos NO están disponibles en ninguna API pública gratuita
(son datos GPS propietarios de Opta/StatsBomb). Se estiman por posición.
"""
from __future__ import annotations
import asyncio
import logging
import re
import unicodedata
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger("fxcbbd.sofascore")

BASE    = "https://api.sofascore.com/api/v1"
TIMEOUT = 12.0

# SofaScore requiere estos headers para no ser rechazado
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Referer":        "https://www.sofascore.com/",
    "Accept":         "application/json, text/plain, */*",
    "Accept-Language":"en-US,en;q=0.9,es;q=0.8",
    "Origin":         "https://www.sofascore.com",
}

# Caché diario: (norm_home, norm_away) → sofa_event_id
_EVENT_CACHE: dict[str, int] = {}
_CACHE_DATE:  str = ""


# ── Normalización de nombres de equipos ──────────────────────────────────────

_NOISE = re.compile(
    r'\b(FC|CF|SC|AC|AS|SS|US|SD|RC|RCD|CD|UD|AD|Athletic|Atletico|'
    r'Club|Futbol|Football|Soccer|Real|Sporting|Deportivo|United|City|'
    r'International|Inter|SV|VfB|VfL|TSG|RB|BSC|FK|SK|HNK|NK)\b',
    re.IGNORECASE,
)

def _norm(name: str) -> str:
    """Normaliza nombre de equipo para comparación fuzzy."""
    # Quitar acentos
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_ = "".join(c for c in nfkd if not unicodedata.combining(c))
    # Minúsculas, quitar ruido
    clean = _NOISE.sub("", ascii_).lower()
    clean = re.sub(r"[^a-z0-9 ]", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean

def _teams_match(sofa_home: str, sofa_away: str, our_home: str, our_away: str) -> bool:
    """True si los nombres de equipo corresponden (fuzzy)."""
    sh, sa = _norm(sofa_home), _norm(sofa_away)
    oh, oa = _norm(our_home),  _norm(our_away)
    def _sim(a: str, b: str) -> bool:
        return a in b or b in a or a[:5] == b[:5]
    return _sim(sh, oh) and _sim(sa, oa)


# ── Fetch genérico ─────────────────────────────────────────────────────────────

async def _get(path: str, params: dict | None = None) -> dict:
    url = f"{BASE}{path}"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, headers=_HEADERS) as c:
            r = await c.get(url, params=params or {})
            if r.status_code == 200:
                return r.json()
            logger.debug("SofaScore HTTP %s: %s", r.status_code, url)
    except Exception as e:
        logger.debug("SofaScore error %s: %s", url, e)
    return {}


# ── Construir caché de eventos del día ────────────────────────────────────────

async def _build_event_cache(date_str: str) -> None:
    global _EVENT_CACHE, _CACHE_DATE
    if _CACHE_DATE == date_str and _EVENT_CACHE:
        return

    d = await _get(f"/sport/football/scheduled-events/{date_str}")
    events = d.get("events", [])
    new_cache: dict[str, int] = {}
    for ev in events:
        home = ev.get("homeTeam", {}).get("name", "")
        away = ev.get("awayTeam", {}).get("name", "")
        eid  = ev.get("id", 0)
        if home and away and eid:
            key = f"{_norm(home)}|{_norm(away)}"
            new_cache[key] = eid
    _EVENT_CACHE = new_cache
    _CACHE_DATE  = date_str
    logger.info("SofaScore cache: %d eventos para %s", len(new_cache), date_str)


async def find_event_id(home: str, away: str) -> Optional[int]:
    """Busca el ID de SofaScore para un partido dado home vs away hoy."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    await _build_event_cache(today)

    # Búsqueda exacta en caché
    key = f"{_norm(home)}|{_norm(away)}"
    if key in _EVENT_CACHE:
        return _EVENT_CACHE[key]

    # Búsqueda fuzzy
    oh, oa = _norm(home), _norm(away)
    for cached_key, eid in _EVENT_CACHE.items():
        ch, ca = cached_key.split("|", 1)
        def _sim(a, b): return a in b or b in a or a[:5] == b[:5]
        if _sim(oh, ch) and _sim(oa, ca):
            return eid

    logger.debug("SofaScore: partido no encontrado %s vs %s", home, away)
    return None


# ── Extraer estadísticas de jugadores ─────────────────────────────────────────

def _extract_player_stats(lineup_data: dict, match_min: int) -> list[dict]:
    """
    Procesa el endpoint /event/{id}/lineups de SofaScore.
    Devuelve lista de equipos con jugadores y sus stats reales.
    """
    from services.player_stats import _km_estimate   # reusar estimador de km

    teams_out = []

    for team_key in ("home", "away"):
        team_block = lineup_data.get(team_key, {})
        team_name  = (team_block.get("team") or {}).get("name", team_key.title())
        players_raw= team_block.get("players", [])

        if not players_raw:
            continue

        players = []
        for entry in players_raw:
            ply  = entry.get("player", {})
            name = ply.get("name", "?")
            pos_obj = entry.get("position", "")
            if isinstance(pos_obj, dict):
                pos = pos_obj.get("abbreviation", "CM")
            else:
                pos = str(pos_obj) or "CM"

            jersey  = str(entry.get("jerseyNumber", "?"))
            starter = entry.get("substitute") is False or entry.get("position") == "G"
            # SofaScore: substitute=True → es suplente
            is_sub  = bool(entry.get("substitute", False))
            starter = not is_sub
            active  = True   # SofaScore incluye solo activos en el lineup

            # ── Stats reales de SofaScore ─────────────────────────────────
            raw_stats = entry.get("statistics", {})

            def gs(k, default=0):
                v = raw_stats.get(k, default)
                try: return float(v or 0)
                except: return float(default)

            # Estadísticas disponibles en SofaScore
            min_played  = gs("minutesPlayed", match_min if starter else 0)
            rating_sofa = gs("rating", 0)              # 0–10 (clave diferenciadora)
            total_pass  = gs("totalPass", 0)
            acc_pass    = gs("accuratePass", 0)
            key_pass    = gs("keyPass", 0)
            total_shot  = gs("totalScoringAtt", 0) or gs("totalShots", 0)
            shot_on_tgt = gs("onTargetScoringAttempt", 0) or gs("shotOnTarget", 0)
            goals       = gs("goals", 0)
            assists     = gs("goalAssist", 0)
            tackle_won  = gs("wonTackle", 0) or gs("totalTackle", 0)
            interc      = gs("interceptionWon", 0) or gs("interceptions", 0)
            clearances  = gs("totalClearance", 0)
            blocks      = gs("blocked", 0) or gs("blockedScoringAttempt", 0)
            fouls_comm  = gs("foulCommitted", 0) or gs("fouls", 0)
            fouls_drawn = gs("foulGiven", 0)
            yellow_c    = gs("yellowCard", 0) or gs("bookings", 0)
            red_c       = gs("redCard", 0)
            duel_won    = gs("duelWon", 0)
            duel_lost   = gs("duelLost", 0)
            aerial_won  = gs("aerialWon", 0)
            aerial_lost = gs("aerialLost", 0)
            dribble_won = gs("successfulDribble", 0)
            dribble_att = gs("attemptedDribble", 0) or gs("totalAttemptAssist", 0)
            long_ball   = gs("totalLongBalls", 0)
            long_ball_ok= gs("accurateLongBalls", 0)
            cross_att   = gs("totalCross", 0)
            cross_ok    = gs("accurateCross", 0)
            touches     = gs("touches", total_pass + total_shot + blocks + interc + tackle_won + 5)

            # Toques OK / Errados (pases acertados + acciones defensivas exitosas)
            toques_ok  = int(acc_pass + tackle_won + interc + blocks + dribble_won + shot_on_tgt)
            toques_err = int(max(0, (total_pass - acc_pass) + (dribble_att - dribble_won) + (total_shot - shot_on_tgt)))
            precision  = round(toques_ok / max(1, toques_ok + toques_err) * 100, 1)

            km = _km_estimate(pos, int(min_played) or match_min, name)

            # ── Balance 0–100 usando rating SofaScore como ancla ──────────
            if rating_sofa > 0:
                # SofaScore rating (0–10) → convertir a escala (0–100)
                balance = round(min(100, max(0,
                    rating_sofa * 8.5           # ancla principal
                    + goals  * 5
                    + assists * 3
                    + shot_on_tgt * 1.5
                    - fouls_comm * 1.5
                    - yellow_c   * 4
                    - red_c      * 15
                )), 1)
            else:
                balance = round(min(100, max(0,
                    precision * 0.40
                    + goals   * 15
                    + assists * 10
                    + shot_on_tgt * 4
                    + tackle_won  * 3
                    + interc      * 2
                    - fouls_comm  * 3
                    - yellow_c    * 8
                    - red_c       * 25
                )), 1)

            # ── Radar (5 ejes 0–100) ─────────────────────────────────────
            radar = {
                "precision":  precision,
                "km":         round(min(100, km / 13 * 100), 1),
                "ofensiva":   round(min(100, goals*18 + assists*12 + shot_on_tgt*6 + dribble_won*3), 1),
                "defensiva":  round(min(100, tackle_won*9 + interc*7 + clearances*5 + blocks*6), 1),
                "disciplina": round(max(0, 100 - fouls_comm*5 - yellow_c*15 - red_c*40), 1),
            }

            players.append({
                "name":       name,
                "jersey":     jersey,
                "pos":        pos,
                "starter":    starter,
                "active":     active,
                "min":        int(min_played),
                # Stats reales SofaScore
                "rating":     round(rating_sofa, 1),    # 0-10, la joya de SofaScore
                "toques":     int(touches),
                "toques_ok":  toques_ok,
                "toques_err": toques_err,
                "precision":  precision,
                "km":         km,
                "km_source":  "estimado",               # honesto: km no disponible gratis
                "goles":      int(goals),
                "asist":      int(assists),
                "tiros":      int(total_shot),
                "tiros_ok":   int(shot_on_tgt),
                "pases":      int(total_pass),
                "pases_ok":   int(acc_pass),
                "pases_clave":int(key_pass),
                "duelos_won": int(duel_won),
                "duelos_lost":int(duel_lost),
                "aereos_won": int(aerial_won),
                "aereos_lost":int(aerial_lost),
                "dribbles":   int(dribble_won),
                "faltas":     int(fouls_comm),
                "faltas_rec": int(fouls_drawn),
                "amarillas":  int(yellow_c),
                "rojas":      int(red_c),
                "bloqueos":   int(blocks),
                "interc":     int(interc),
                "tackeos":    int(tackle_won),
                "despejes":   int(clearances),
                "lesionado":  False,
                "balance":    balance,
                "radar":      radar,
            })

        if not players:
            continue

        starters = [p for p in players if p["starter"]]
        subs     = [p for p in players if not p["starter"]]

        # Balance equipo
        def team_avg(field): return round(sum(p[field] for p in starters) / max(1, len(starters)), 1)

        team_km        = round(sum(p["km"]       for p in starters), 1)
        team_toques    = sum(p["toques"]          for p in starters)
        team_toques_ok = sum(p["toques_ok"]       for p in starters)
        team_precision = round(team_toques_ok / max(1, team_toques) * 100, 1)
        team_goles     = sum(p["goles"]           for p in starters)
        team_asist     = sum(p["asist"]           for p in starters)
        team_faltas    = sum(p["faltas"]           for p in starters)
        team_balance   = team_avg("balance")
        team_rating    = round(sum(p["rating"] for p in starters if p["rating"] > 0)
                               / max(1, sum(1 for p in starters if p["rating"] > 0)), 2)
        team_radar     = {
            k: round(sum(p["radar"][k] for p in starters) / max(1, len(starters)), 1)
            for k in ["precision", "km", "ofensiva", "defensiva", "disciplina"]
        }
        # MVP: jugador con mayor rating (o balance)
        best = max(starters, key=lambda p: p["rating"] if p["rating"] > 0 else p["balance"], default=None)

        teams_out.append({
            "team":           team_name,
            "team_id":        (team_block.get("team") or {}).get("id", ""),
            "home_away":      team_key,
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
            "team_rating":    team_rating,
            "team_radar":     team_radar,
            "mvp":            best["name"] if best else None,
            "mvp_rating":     best["rating"] if best else 0,
            "lesionados":     [],
            "source":         "sofascore",
        })

    return teams_out


# ── Función principal ─────────────────────────────────────────────────────────

async def fetch_sofascore_players(
    home: str,
    away: str,
    match_min: int = 45,
    sofa_event_id: Optional[int] = None,
) -> dict:
    """
    Obtiene estadísticas REALES de jugadores desde SofaScore.

    Args:
        home: Nombre del equipo local (para buscar en SofaScore)
        away: Nombre del equipo visitante
        match_min: Minuto actual del partido
        sofa_event_id: ID SofaScore si se conoce (evita la búsqueda)

    Returns:
        dict con teams[], source="sofascore", clock, etc.
    """
    # 1. Encontrar el ID del evento en SofaScore
    eid = sofa_event_id
    if not eid:
        eid = await find_event_id(home, away)
    if not eid:
        return {"error": f"Partido '{home} vs {away}' no encontrado en SofaScore para hoy", "teams": []}

    # 2. Obtener alineaciones + stats
    lineup_data = await _get(f"/event/{eid}/lineups")
    if not lineup_data:
        return {"error": f"SofaScore no tiene alineaciones para el evento {eid}", "teams": []}

    teams = _extract_player_stats(lineup_data, match_min)
    if not teams:
        return {"error": "Sin datos de jugadores en SofaScore para este partido", "teams": []}

    # 3. Obtener también estadísticas del partido (posesión, etc.) para enriquecer
    event_data   = await _get(f"/event/{eid}")
    status_obj   = (event_data.get("event") or {}).get("status", {})
    status_desc  = status_obj.get("description", "")
    clock        = f"{match_min}'" if match_min else status_desc

    return {
        "sofa_event_id": eid,
        "source":        "sofascore",
        "clock":         clock,
        "match_min":     match_min,
        "teams":         teams,
    }
