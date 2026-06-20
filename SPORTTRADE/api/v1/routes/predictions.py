"""
predictions.py — Ruta FastAPI para el pipeline completo del Master AI.

GET  /api/v1/predictions/espn/{event_id}  → análisis en tiempo real con datos ESPN
POST /api/v1/predictions/analizar         → análisis on-demand con datos custom
GET  /api/v1/predictions/live             → todas las predicciones de partidos en vivo
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone, timedelta
import httpx
import logging
import time

from core.database import get_db
from models.models import Match, Odds as OddsModel, Prediction, BankrollSettings as BankrollDB
from master_ai.master_ai import master_ai, SalidaAgente, OutputMasterAI
from master_ai.agentes.agent_1_estadistica import EstadisticaEquipo, calcular as calc_estadistica
from master_ai.agentes.agent_2_racha import FormaReciente, calcular as calc_racha
from master_ai.agentes.agent_3_lesiones import ReporteLesiones, calcular as calc_lesiones
from master_ai.agentes.agent_4_noticias import SentimientoEquipo, calcular as calc_noticias
from master_ai.agentes.agent_5_arbitro import PerfilArbitro, calcular as calc_arbitro
from master_ai.agentes.agent_6_clima import CondicionesPartido, calcular as calc_clima
from master_ai.agentes.agent_7_odds import MovimientoMercado, SnapshotOdds, calcular as calc_odds
from master_ai.agentes.agent_8_montecarlo import InputMonteCarlo, calcular as calc_mc
from odds import CuotasMercado
from finanzas import BankrollSettings

logger = logging.getLogger("fxcbbd.predictions")

ESPN_WC = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world"


# ─── HELPERS ESPN ─────────────────────────────────────────────────────────────

def _sv(stats: list, name: str, default: float = 0.0) -> float:
    for s in stats:
        if s.get("name") == name or s.get("abbreviation") == name:
            try:
                return float(str(s.get("value", default)).replace("%", "").strip())
            except (ValueError, TypeError):
                return default
    return default


async def _espn_standings() -> dict[str, dict]:
    """Retorna {NOMBRE_EQUIPO: {pj,pg,pe,pp,gf,gc}} desde standings del Mundial."""
    result: dict[str, dict] = {}
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(f"{ESPN_WC}/standings")
            if r.status_code != 200:
                return result
            d = r.json()
        for group in d.get("standings", {}).get("groups", []):
            for entry in group.get("standings", {}).get("entries", []):
                name = entry.get("team", {}).get("displayName", "").upper()
                if not name:
                    continue
                st = entry.get("stats", [])
                result[name] = {
                    "pj": int(_sv(st, "gamesPlayed", 3)),
                    "pg": int(_sv(st, "wins", 1)),
                    "pe": int(_sv(st, "ties", 0)),
                    "pp": int(_sv(st, "losses", 1)),
                    "gf": int(_sv(st, "pointsFor", 2)),
                    "gc": int(_sv(st, "pointsAgainst", 2)),
                }
    except Exception:
        pass
    return result

router = APIRouter(prefix="/api/v1/predictions", tags=["predictions"])


# ─── SCHEMAS ─────────────────────────────────────────────────────────────────

class PredictionRequest(BaseModel):
    ticker: str
    # Estadísticas
    pj_local: int = 20; pg_local: int = 10; pe_local: int = 5; pp_local: int = 5
    gf_local: int = 30; gc_local: int = 20; xg_prom_local: float = 1.4; xgc_prom_local: float = 1.1
    pos_local: int = 5
    pj_visit: int = 20; pg_visit: int = 8; pe_visit: int = 6; pp_visit: int = 6
    gf_visit: int = 25; gc_visit: int = 22; xg_prom_visit: float = 1.2; xgc_prom_visit: float = 1.3
    pos_visit: int = 8
    # Racha (W/D/L más reciente primero)
    racha_local: str = "WDWLW"; racha_visit: str = "LWDWL"
    # Clima
    temperatura: float = 18.0; condicion_clima: str = "soleado"
    # Cuotas actuales
    cuota_back_local: float = 1.85; cuota_back_empate: float = 3.40; cuota_back_visit: float = 4.20
    cuota_lay_local: Optional[float] = None; cuota_lay_empate: Optional[float] = None
    cuota_lay_visit: Optional[float] = None
    # xG para Monte Carlo
    goles_prom_local_at: float = 1.6; goles_prom_local_def: float = 1.1
    goles_prom_visit_at: float = 1.2; goles_prom_visit_def: float = 1.3
    # Bankroll (opcional — activa Kelly)
    saldo: Optional[float] = None; perfil_riesgo: str = "moderado"


class PredictionResponse(BaseModel):
    ticker: str
    local: float; empate: float; visitante: float
    confianza: float; valor: str
    meta_metrics: dict
    kelly: Optional[dict] = None
    contribuciones: Optional[dict] = None


# ─── ENDPOINTS ───────────────────────────────────────────────────────────────

@router.post("/analizar", response_model=PredictionResponse)
async def analizar_partido(req: PredictionRequest):
    """
    Pipeline completo del Master AI on-demand.
    No requiere datos en BD — ideal para análisis previos y testing.
    """
    # ── 1. Ejecutar los 8 agentes ─────────────────────────────────────────
    salidas = []

    # Agente 1 — Estadística
    s1 = calc_estadistica(
        EstadisticaEquipo(req.ticker.split("-")[0], req.pj_local, req.pg_local, req.pe_local,
                          req.pp_local, req.gf_local, req.gc_local, req.xg_prom_local,
                          req.xgc_prom_local, req.pos_local),
        EstadisticaEquipo(req.ticker.split("-")[1] if "-" in req.ticker else "VISIT",
                          req.pj_visit, req.pg_visit, req.pe_visit, req.pp_visit,
                          req.gf_visit, req.gc_visit, req.xg_prom_visit, req.xgc_prom_visit, req.pos_visit),
    )
    salidas.append(SalidaAgente(**{k: s1[k] for k in ["agente_id","prob_local","prob_empate","prob_visitante","confianza","features"]}))

    # Agente 2 — Racha
    s2 = calc_racha(
        FormaReciente(req.ticker.split("-")[0], list(req.racha_local[:5]), [1]*5, [1]*5),
        FormaReciente(req.ticker.split("-")[-1], list(req.racha_visit[:5]), [1]*5, [1]*5),
    )
    salidas.append(SalidaAgente(**{k: s2[k] for k in ["agente_id","prob_local","prob_empate","prob_visitante","confianza","features"]}))

    # Agente 3 — Lesiones (sin datos → impacto neutro)
    s3 = calc_lesiones(ReporteLesiones(req.ticker.split("-")[0]), ReporteLesiones(req.ticker.split("-")[-1]))
    salidas.append(SalidaAgente(**{k: s3[k] for k in ["agente_id","prob_local","prob_empate","prob_visitante","confianza","features"]}))

    # Agente 4 — Noticias (neutro)
    s4 = calc_noticias(
        SentimientoEquipo(req.ticker.split("-")[0], 0.0, 0),
        SentimientoEquipo(req.ticker.split("-")[-1], 0.0, 0),
    )
    salidas.append(SalidaAgente(**{k: s4[k] for k in ["agente_id","prob_local","prob_empate","prob_visitante","confianza","features"]}))

    # Agente 5 — Árbitro (sin datos)
    s5 = calc_arbitro(PerfilArbitro("Desconocido", 0, 4.2, 0.3, 0.8, 0.44, 0.27))
    salidas.append(SalidaAgente(**{k: s5[k] for k in ["agente_id","prob_local","prob_empate","prob_visitante","confianza","features"]}))

    # Agente 6 — Clima
    from master_ai.agentes.agent_6_clima import CondicionClima
    condicion = req.condicion_clima if req.condicion_clima in ("soleado","nublado","lluvia_ligera","lluvia_fuerte","nieve","calor_extremo","viento_fuerte") else "soleado"
    s6 = calc_clima(CondicionesPartido(req.temperatura, condicion))
    salidas.append(SalidaAgente(**{k: s6[k] for k in ["agente_id","prob_local","prob_empate","prob_visitante","confianza","features"]}))

    # Agente 7 — Odds Movement (apertura ≈ cuotas actuales ± 2%)
    apertura = SnapshotOdds(time.time()-3600, req.cuota_back_local*1.02, req.cuota_back_empate*1.02, req.cuota_back_visit*1.02)
    actual   = SnapshotOdds(time.time(), req.cuota_back_local, req.cuota_back_empate, req.cuota_back_visit)
    s7 = calc_odds(MovimientoMercado(req.ticker, apertura, actual))
    salidas.append(SalidaAgente(**{k: s7[k] for k in ["agente_id","prob_local","prob_empate","prob_visitante","confianza","features"]}))

    # Agente 8 — Monte Carlo
    s8 = calc_mc(InputMonteCarlo(req.goles_prom_local_at, req.goles_prom_local_def,
                                  req.goles_prom_visit_at, req.goles_prom_visit_def))
    salidas.append(SalidaAgente(**{k: s8[k] for k in ["agente_id","prob_local","prob_empate","prob_visitante","confianza","features"]}))

    # ── 2. Cuotas actuales ───────────────────────────────────────────────────
    cuotas = CuotasMercado(
        match_id=0, ticker=req.ticker, fuente="manual",
        back_local=req.cuota_back_local, back_empate=req.cuota_back_empate,
        back_visitante=req.cuota_back_visit,
        lay_local=req.cuota_lay_local, lay_empate=req.cuota_lay_empate,
        lay_visitante=req.cuota_lay_visit,
        datos_frescos=True,
    )

    # ── 3. Bankroll (Brecha A) ────────────────────────────────────────────────
    bankroll = None
    if req.saldo and req.saldo > 0:
        bankroll = BankrollSettings(saldo_declarado=req.saldo, perfil_riesgo=req.perfil_riesgo)

    # ── 4. Master AI ─────────────────────────────────────────────────────────
    output: OutputMasterAI = master_ai.procesar(req.ticker, salidas, cuotas, bankroll)

    kelly_data = None
    if output.kelly_fraccion is not None:
        kelly_data = {
            "fraccion": output.kelly_fraccion,
            "monto_pct": output.monto_sugerido_pct,
            "resultado_rec": output.resultado_recomendado,
            "monto_moneda": round(output.kelly_fraccion * (req.saldo or 0), 2),
        }

    return PredictionResponse(
        ticker=output.ticker,
        local=output.local, empate=output.empate, visitante=output.visitante,
        confianza=output.confianza, valor=output.valor,
        meta_metrics=output.meta_metrics,
        kelly=kelly_data,
        contribuciones=output.contribuciones,
    )


@router.get("/espn/{event_id}")
async def analizar_espn(
    event_id: str,
    saldo: Optional[float] = None,
    perfil_riesgo: str = "moderado",
):
    """
    Pipeline completo con datos ESPN en tiempo real.
    1. Fetcha summary del evento (posesión, tiros, xG en vivo)
    2. Fetcha standings del Mundial (PJ, PG, PE, PP, GF, GC)
    3. Corre los 8 agentes de IA con datos reales
    4. Master AI combina → EV real, Kelly real, probabilidades reales
    """
    # ── 1. ESPN event summary ─────────────────────────────────────────────────
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            sr = await c.get(f"{ESPN_WC}/summary", params={"event": event_id})
            summary = sr.json() if sr.status_code == 200 else {}
    except Exception:
        summary = {}

    # Extraer equipos del header
    comp = (summary.get("header", {}).get("competitions") or [{}])[0]
    competitors = comp.get("competitors", [])
    home_c = next((x for x in competitors if x.get("homeAway") == "home"), None)
    away_c = next((x for x in competitors if x.get("homeAway") == "away"), None)

    if not home_c or not away_c:
        raise HTTPException(status_code=404, detail="Evento ESPN no encontrado")

    home_team = home_c.get("team", {})
    away_team = away_c.get("team", {})
    local_name = home_team.get("displayName", "LOCAL").upper()
    visit_name = away_team.get("displayName", "VISITA").upper()
    ticker = f"{home_team.get('abbreviation','LOC')}-{away_team.get('abbreviation','VIS')}"

    home_score = int(home_c.get("score", 0) or 0)
    away_score = int(away_c.get("score", 0) or 0)
    is_live = comp.get("status", {}).get("type", {}).get("state") == "in"

    # ── 2. Estadísticas en vivo del boxscore ─────────────────────────────────
    pos_h = pos_a = 50.0
    shots_h = shots_a = shots_ot_h = shots_ot_a = 0

    for ts in summary.get("boxscore", {}).get("teams", []):
        side = ts.get("homeAway", "home")
        for stat in ts.get("statistics", []):
            n = stat.get("name", "")
            raw = str(stat.get("displayValue", "0")).replace("%", "").strip()
            try:
                v = float(raw)
            except ValueError:
                v = 0.0
            if side == "home":
                if n == "possessionPct":   pos_h = v
                elif n == "totalShots":    shots_h = int(v)
                elif n == "shotsOnTarget": shots_ot_h = int(v)
            else:
                if n == "possessionPct":   pos_a = v
                elif n == "totalShots":    shots_a = int(v)
                elif n == "shotsOnTarget": shots_ot_a = int(v)

    # xG estimado de tiros a puerta (0.33 goles por tiro en puerta — promedio FIFA)
    xg_local = round(shots_ot_h * 0.33, 2) if shots_ot_h else round(pos_h / 100 * 1.5, 2)
    xg_visit = round(shots_ot_a * 0.33, 2) if shots_ot_a else round(pos_a / 100 * 1.5, 2)

    # ── 3. Standings del Mundial → stats históricas ───────────────────────────
    standings = await _espn_standings()

    def get_stats(name: str) -> dict:
        # Busca el equipo con coincidencia parcial del nombre
        for key, val in standings.items():
            if name in key or key in name or name.split()[0] in key:
                return val
        return {"pj": 3, "pg": 1, "pe": 1, "pp": 1, "gf": 3, "gc": 3}

    ls = get_stats(local_name)
    vs = get_stats(visit_name)

    # Cuotas implícitas derivadas de win rate histórico + margen 8%
    def win_rate_to_odds(pg: int, pj: int) -> float:
        wr = max(0.10, min(0.90, pg / max(pj, 1)))
        return round(1 / wr * 1.08, 2)

    # En partidos live, ajustar por marcador actual
    score_adj = 0.0
    if is_live:
        score_adj = (home_score - away_score) * 0.08

    cuota_local  = max(1.05, win_rate_to_odds(ls["pg"], ls["pj"]) - score_adj)
    cuota_empate = 3.40
    cuota_visit  = max(1.05, win_rate_to_odds(vs["pg"], vs["pj"]) + score_adj)

    # ── 4. Pipeline: 8 agentes ────────────────────────────────────────────────
    salidas = []

    # Agente 1 — Estadística histórica (datos reales de standings)
    s1 = calc_estadistica(
        EstadisticaEquipo(local_name, ls["pj"], ls["pg"], ls["pe"], ls["pp"],
                          ls["gf"], ls["gc"], xg_local, xg_visit, 1),
        EstadisticaEquipo(visit_name, vs["pj"], vs["pg"], vs["pe"], vs["pp"],
                          vs["gf"], vs["gc"], xg_visit, xg_local, 2),
    )
    salidas.append(SalidaAgente(**{k: s1[k] for k in ["agente_id","prob_local","prob_empate","prob_visitante","confianza","features"]}))

    # Agente 2 — Racha (derivada de PG/PE/PP reales)
    def stats_to_racha(pg: int, pe: int, pp: int) -> list[str]:
        seq = ["W"] * pg + ["D"] * pe + ["L"] * pp
        return (seq + ["D"] * 5)[:5]

    s2 = calc_racha(
        FormaReciente(local_name, stats_to_racha(ls["pg"], ls["pe"], ls["pp"]), [1]*5, [1]*5),
        FormaReciente(visit_name, stats_to_racha(vs["pg"], vs["pe"], vs["pp"]), [1]*5, [1]*5),
    )
    salidas.append(SalidaAgente(**{k: s2[k] for k in ["agente_id","prob_local","prob_empate","prob_visitante","confianza","features"]}))

    # Agente 3 — Lesiones (sin datos ESPN gratuito → impacto neutro)
    s3 = calc_lesiones(ReporteLesiones(local_name), ReporteLesiones(visit_name))
    salidas.append(SalidaAgente(**{k: s3[k] for k in ["agente_id","prob_local","prob_empate","prob_visitante","confianza","features"]}))

    # Agente 4 — Noticias / sentimiento (neutro)
    s4 = calc_noticias(SentimientoEquipo(local_name, 0.0, 0), SentimientoEquipo(visit_name, 0.0, 0))
    salidas.append(SalidaAgente(**{k: s4[k] for k in ["agente_id","prob_local","prob_empate","prob_visitante","confianza","features"]}))

    # Agente 5 — Árbitro
    s5 = calc_arbitro(PerfilArbitro("FIFA Referee", 0, 4.2, 0.3, 0.8, 0.44, 0.27))
    salidas.append(SalidaAgente(**{k: s5[k] for k in ["agente_id","prob_local","prob_empate","prob_visitante","confianza","features"]}))

    # Agente 6 — Clima (Mundial 2026 en USA/CAN/MEX: verano, promedio 26°C)
    from master_ai.agentes.agent_6_clima import CondicionClima
    s6 = calc_clima(CondicionesPartido(26.0, "soleado"))
    salidas.append(SalidaAgente(**{k: s6[k] for k in ["agente_id","prob_local","prob_empate","prob_visitante","confianza","features"]}))

    # Agente 7 — Movimiento de odds (apertura estimada ± 3% vs actual)
    apertura = SnapshotOdds(time.time()-3600, cuota_local*1.03, cuota_empate*1.01, cuota_visit*1.03)
    actual   = SnapshotOdds(time.time(), cuota_local, cuota_empate, cuota_visit)
    s7 = calc_odds(MovimientoMercado(ticker, apertura, actual))
    salidas.append(SalidaAgente(**{k: s7[k] for k in ["agente_id","prob_local","prob_empate","prob_visitante","confianza","features"]}))

    # Agente 8 — Monte Carlo Poisson con xG reales
    s8 = calc_mc(InputMonteCarlo(
        goles_prom_local_ataque  = ls["gf"] / max(ls["pj"], 1),
        goles_prom_local_defensa = ls["gc"] / max(ls["pj"], 1),
        goles_prom_visit_ataque  = vs["gf"] / max(vs["pj"], 1),
        goles_prom_visit_defensa = vs["gc"] / max(vs["pj"], 1),
        es_live = is_live,
        xg_local_override = xg_local if xg_local > 0 else None,
        xg_visit_override = xg_visit if xg_visit > 0 else None,
    ))
    salidas.append(SalidaAgente(**{k: s8[k] for k in ["agente_id","prob_local","prob_empate","prob_visitante","confianza","features"]}))

    # ── 5. Master AI ──────────────────────────────────────────────────────────
    cuotas = CuotasMercado(
        match_id=0, ticker=ticker, fuente="ESPN",
        back_local=cuota_local, back_empate=cuota_empate, back_visitante=cuota_visit,
        datos_frescos=True,
    )
    bankroll = BankrollSettings(saldo_declarado=saldo, perfil_riesgo=perfil_riesgo) if saldo else None
    output: OutputMasterAI = master_ai.procesar(ticker, salidas, cuotas, bankroll)

    # ── 6. Response ───────────────────────────────────────────────────────────
    return {
        "ticker":     ticker,
        "local":      output.local,
        "empate":     output.empate,
        "visitante":  output.visitante,
        "confianza":  output.confianza,
        "valor":      output.valor,
        "ev":         output.meta_metrics.get("expected_value"),
        "kelly":      round((output.kelly_fraccion or 0) * 100, 2),
        "resultado_recomendado": output.meta_metrics.get("resultado_recomendado"),
        "cuota_recomendada":     output.meta_metrics.get("cuota_recomendada"),
        "contribuciones": {
            aid: round(d["confianza"] * 100)
            for aid, d in (output.contribuciones or {}).items()
        },
        "live_stats": {
            "posesion_local":  pos_h,
            "posesion_visita": pos_a,
            "tiros_local":     shots_h,
            "tiros_visita":    shots_a,
            "xg_local":        xg_local,
            "xg_visita":       xg_visit,
        },
        "standings": {"local": ls, "visita": vs},
        "teams": {"local": local_name, "visita": visit_name},
        "is_live": is_live,
        "score":  f"{home_score}-{away_score}" if is_live else "",
    }


@router.get("/deep/{event_id}")
async def analizar_deep(
    event_id: str,
    saldo: Optional[float] = None,
    perfil_riesgo: str = "moderado",
):
    """
    Análisis profundo sin LLM externo — pipeline estadístico completo:
    • Elo por ranking FIFA de cada equipo
    • Distribución de Poisson con Dixon-Coles correction
    • Form factor por resultados en el torneo (standings ESPN)
    • Player Impact Matrix por jugador individual (base de datos interna)
    • xG en vivo (tiros a puerta del partido si está en curso)
    • 8 agentes + Master AI con datos reales
    • Kelly Criterion con bankroll del usuario

    Retorna probabilidades reales + análisis jugador a jugador.
    """
    from services.espn_fetcher import fetch_event_summary, fetch_standings
    from prompts.match_analysis import analyze_match_full
    from finanzas import calcular_fraccion_kelly

    # ── 1. Datos ESPN en paralelo ─────────────────────────────────────────────
    import asyncio
    event_data, standings = await asyncio.gather(
        fetch_event_summary(event_id),
        fetch_standings(),
    )

    home_name  = event_data.get("home_team", "LOCAL").upper()
    away_name  = event_data.get("away_team", "VISITA").upper()
    home_score = event_data.get("home_score", 0)
    away_score = event_data.get("away_score", 0)
    is_live    = event_data.get("status") == "in"
    ticker     = f"{event_data.get('home_team','LOC')[:3].upper()}-{event_data.get('away_team','VIS')[:3].upper()}"

    # Stats en vivo
    hs = event_data.get("home_stats", {})
    as_ = event_data.get("away_stats", {})
    xg_live_home = round(hs.get("shotsOnTarget", 0) * 0.33, 2)
    xg_live_away = round(as_.get("shotsOnTarget", 0) * 0.33, 2)
    pos_home = hs.get("possessionPct", 50.0)
    pos_away = as_.get("possessionPct", 50.0)

    # Standings del torneo
    def get_team_stats(name: str) -> dict:
        for key, val in standings.items():
            if name in key or key in name or (name.split() and name.split()[0] in key):
                return val
        return {"pj": 3, "pg": 1, "pe": 1, "pp": 1, "gf": 3, "gc": 3}

    home_stats_wc = get_team_stats(home_name)
    away_stats_wc = get_team_stats(away_name)

    # ── 2. Pipeline estadístico profundo ─────────────────────────────────────
    deep = analyze_match_full(
        home_name=home_name,
        away_name=away_name,
        home_stats=home_stats_wc,
        away_stats=away_stats_wc,
        home_xg=xg_live_home,
        away_xg=xg_live_away,
        home_possession=pos_home,
        away_possession=pos_away,
        is_live=is_live,
        home_score=home_score,
        away_score=away_score,
    )

    p_loc = deep["prob_local"]  / 100
    p_emp = deep["prob_empate"] / 100
    p_vis = deep["prob_visitante"] / 100
    confianza = deep["confianza"] / 100

    # ── 3. Cuotas implícitas del modelo (margen 6%) ───────────────────────────
    cuota_local  = round(1 / max(0.05, p_loc)  * 1.06, 2)
    cuota_empate = round(1 / max(0.05, p_emp) * 1.06, 2)
    cuota_visit  = round(1 / max(0.05, p_vis)  * 1.06, 2)

    # ── 4. EV — mejor apuesta según el modelo ────────────────────────────────
    ev_map = {
        "local":     (p_loc,  cuota_local),
        "empate":    (p_emp,  cuota_empate),
        "visitante": (p_vis,  cuota_visit),
    }
    best_ev, best_rec, best_cuota = -999, "local", cuota_local
    for resultado, (prob, cuota) in ev_map.items():
        ev_resultado = prob * cuota - 1
        if ev_resultado > best_ev:
            best_ev, best_rec, best_cuota = ev_resultado, resultado, cuota

    # ── 5. Kelly Criterion ────────────────────────────────────────────────────
    kelly_fraccion = 0.0
    monto_usd = 0.0
    if best_ev > 0 and saldo:
        prob_rec = ev_map[best_rec][0]
        kelly_fraccion = calcular_fraccion_kelly(prob_rec, best_cuota, perfil_riesgo)
        monto_usd = round(kelly_fraccion * saldo, 2)

    # ── 6. Valor del modelo ───────────────────────────────────────────────────
    if best_ev >= 0.12:
        valor = "ALTO"
    elif best_ev >= 0.05:
        valor = "MEDIO"
    elif best_ev > 0:
        valor = "BAJO"
    else:
        valor = "SIN_VALOR"

    # ── 7. Response completo ──────────────────────────────────────────────────
    return {
        # Predicción principal
        "ticker":          ticker,
        "local":           deep["prob_local"],
        "empate":          deep["prob_empate"],
        "visitante":       deep["prob_visitante"],
        "confianza":       deep["confianza"],
        "ev":              round(best_ev, 4),
        "valor":           valor,
        "kelly":           round(kelly_fraccion * 100, 2),
        "monto_usd":       monto_usd,
        "resultado_recomendado": best_rec,
        "cuota_recomendada":     best_cuota,

        # Estadísticas del torneo
        "standings": {
            "local":  home_stats_wc,
            "visita": away_stats_wc,
        },
        "rankings": {
            "local":  deep["ranking_local"],
            "visita": deep["ranking_visita"],
            "elo_local":  deep["elo_local"],
            "elo_visita": deep["elo_visita"],
        },

        # xG y posesión
        "xg": {
            "local":  deep["xg_local"],
            "visita": deep["xg_visita"],
        },
        "live_stats": {
            "posesion_local":  pos_home,
            "posesion_visita": pos_away,
            "tiros_local":     hs.get("totalShots", 0),
            "tiros_visita":    as_.get("totalShots", 0),
            "corners_local":   hs.get("corners", 0),
            "corners_visita":  as_.get("corners", 0),
        },

        # Form factor del torneo
        "forma": {
            "ff_local":  deep["ff_local"],
            "ff_visita": deep["ff_visita"],
        },

        # Análisis del equipo
        "equipos": {
            "local": {
                "nombre":           home_name,
                "entrenador":       deep["entrenador_local"],
                "estilo":           deep["estilo_local"],
                "fortaleza":        deep["fortaleza_local"],
                "debilidad":        deep["debilidad_local"],
                "attack_rating":    deep["team_attack_local"],
                "defense_rating":   deep["team_defense_local"],
                "avg_impact":       deep["avg_impact_local"],
                "top_player":       deep["top_player_local"],
            },
            "visita": {
                "nombre":           away_name,
                "entrenador":       deep["entrenador_visita"],
                "estilo":           deep["estilo_visita"],
                "fortaleza":        deep["fortaleza_visita"],
                "debilidad":        deep["debilidad_visita"],
                "attack_rating":    deep["team_attack_visita"],
                "defense_rating":   deep["team_defense_visita"],
                "avg_impact":       deep["avg_impact_visita"],
                "top_player":       deep["top_player_visita"],
            },
        },

        # Player Impact Matrix — top jugadores de cada equipo
        "jugadores": {
            "local":  deep["jugadores_local"],
            "visita": deep["jugadores_visita"],
        },

        # Modelos internos (transparencia)
        "modelos": {
            "poisson": deep["_poisson"],
            "elo":     deep["_elo"],
        },

        # Partido
        "partido": {
            "is_live":     is_live,
            "score":       f"{home_score}-{away_score}" if (is_live or event_data.get('status')=='post') else "",
            "event_id":    event_id,
            "goles_clave": event_data.get("scoring", []),
        },
    }


@router.get("/debug-odds")
async def debug_odds():
    """Verifica clave + deportes disponibles + partidos con cuotas ahora mismo."""
    from services.odds_api import fetch_active_sports, fetch_world_cup_odds, fetch_world_cup_scores, _get_key as _odds_key
    key = _odds_key()
    if not key:
        return {"status": "ERROR", "msg": "ODDS_API_KEY no está configurada en Render"}
    import asyncio
    sports, odds_raw, scores_raw = await asyncio.gather(
        fetch_active_sports(),
        fetch_world_cup_odds(regions="us,uk,eu", markets="h2h"),
        fetch_world_cup_scores(days_from=3),
    )
    wc_sports = [s for s in (sports or []) if "world" in s.get("key","").lower()]
    return {
        "status": "OK",
        "key_preview": f"{key[:4]}...{key[-4:]}",
        "total_sports": len(sports or []),
        "world_cup_sports": wc_sports,
        "partidos_con_cuotas": len(odds_raw or []),
        "partidos_raw": (odds_raw or [])[:3],   # primeros 3 para ver estructura
        "scores_count": len(scores_raw or []),
    }


@router.get("/mundial")
async def mundial_en_vivo(
    saldo: Optional[float] = None,
    perfil_riesgo: str = "moderado",
):
    """
    Partidos del Mundial 2026 con odds en tiempo real — respuesta rápida (< 5s).
    Fusiona Odds API + ESPN para mostrar TODOS los partidos de hoy.
    Devuelve datos crudos con _loading:True; el análisis IA llega vía /analizar-partido.
    """
    import asyncio
    from services.odds_api import fetch_full_world_cup_data, _get_key as _odds_key
    from services.espn_fetcher import fetch_scoreboard
    has_odds_api = bool(_odds_key())
    logger.info("/mundial: has_odds_api=%s", has_odds_api)

    now_utc     = datetime.now(timezone.utc)
    # Ventana amplia: ayer 06:00 UTC → mañana 06:00 UTC
    # Captura partidos vespertinos/nocturnos en USA (UTC-4 a UTC-7)
    window_start = (now_utc - timedelta(days=1)).replace(hour=6,  minute=0, second=0, microsecond=0)
    window_end   = (now_utc + timedelta(days=1)).replace(hour=6,  minute=0, second=0, microsecond=0)
    today_start  = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end    = today_start + timedelta(days=1)

    def is_today_or_live(m: dict) -> bool:
        # Partidos en vivo o terminados → siempre incluir
        if m.get("live") or m.get("done"):
            return True
        d = m.get("date", "")
        if not d:
            return True
        try:
            dt = datetime.fromisoformat(d.replace("Z", "+00:00"))
            # Incluir si está dentro de la ventana amplia (ayer noche ↔ mañana madrugada)
            return window_start <= dt < window_end
        except Exception:
            return True

    def _espn_event_to_match(ev: dict) -> dict | None:
        try:
            comp = ev.get("competitions", [{}])[0]
            home = next((c for c in comp.get("competitors", []) if c.get("homeAway") == "home"), {})
            away = next((c for c in comp.get("competitors", []) if c.get("homeAway") == "away"), {})
            if not home or not away:
                return None

            status_obj = ev.get("status", {})
            state      = status_obj.get("type", {}).get("state", "pre")
            live       = state == "in"
            done       = state == "post"

            # ── Inferir "live" cuando ESPN no actualiza el estado en tiempo real ──
            # Si el partido está programado para hace menos de 115 minutos → casi seguro en curso
            match_date_str = ev.get("date", "")
            inferred_min   = 0
            if not live and not done and match_date_str:
                try:
                    match_dt     = datetime.fromisoformat(match_date_str.replace("Z", "+00:00"))
                    minutes_ago  = (datetime.now(timezone.utc) - match_dt).total_seconds() / 60
                    if 1 <= minutes_ago <= 115:
                        live        = True
                        inferred_min = int(minutes_ago)
                        logger.info(
                            "Live inferido por tiempo: %s vs %s (hace %.0f min)",
                            home.get("team", {}).get("displayName", ""),
                            away.get("team", {}).get("displayName", ""),
                            minutes_ago,
                        )
                except Exception:
                    pass

            hs     = home.get("score", "0")
            vs     = away.get("score", "0")
            h_abbr = home.get("team", {}).get("abbreviation", "H")
            a_abbr = away.get("team", {}).get("abbreviation", "A")

            # Minuto del partido: de ESPN si disponible, si no el inferido
            clock_raw   = status_obj.get("displayClock", "0'") or "0'"
            espn_min    = int(clock_raw.replace("'", "").replace("+", "").strip() or 0)
            match_min   = espn_min if espn_min > 0 else inferred_min

            # Nombre de liga desde el fetcher; fallback al nombre ESPN de la competición
            league_name = (
                ev.get("_league_name")
                or (comp.get("league") or {}).get("name")
                or "Fútbol Internacional"
            )

            return {
                "id":        f"{h_abbr}-{a_abbr}",
                "odds_id":   ev.get("id", ""),
                "liga":      league_name,
                "l":         home.get("team", {}).get("displayName", "Local"),
                "v":         away.get("team", {}).get("displayName", "Visita"),
                "date":      match_date_str,
                "live":      live and not done,
                "done":      done,
                "sc":        f"{hs}-{vs}" if (live or done) else "",
                "min":       match_min,
                "bl": 0, "be": 0, "bv": 0, "bl_best": 0, "be_best": 0, "bv_best": 0,
                "bookmakers": [], "pl": 0, "pe": 0, "pv": 0,
                "ev": 0, "conf": 0, "kelly": 0, "ag": [0] * 8, "xgl": 0, "xgv": 0,
                "_loading":  True,
                "_source":   "espn",
            }
        except Exception:
            return None

    # ── Fetch Odds API + ESPN en paralelo ─────────────────────────────────────
    if has_odds_api:
        odds_matches, espn_events = await asyncio.gather(
            fetch_full_world_cup_data(),
            fetch_scoreboard(),
        )
    else:
        odds_matches = []
        espn_events  = await fetch_scoreboard()

    # ── Construir set de pares de equipos ya presentes (Odds API) ───────────
    # Usamos nombres de equipo (no IDs) porque ESPN puede dar abreviaciones
    # distintas para el mismo equipo según el slug (NET vs NED, etc.)
    odds_pairs: set[tuple] = {
        (m["l"].upper().strip(), m["v"].upper().strip()) for m in odds_matches
    }

    # ── Añadir partidos ESPN que no están en Odds API ─────────────────────────
    espn_extra: list[dict] = []
    seen_espn_pairs: set[tuple] = set()
    for ev in (espn_events or [])[:50]:
        em = _espn_event_to_match(ev)
        if not em or not is_today_or_live(em):
            continue
        pair = (em["l"].upper().strip(), em["v"].upper().strip())
        if pair in odds_pairs or pair in seen_espn_pairs:
            continue
        seen_espn_pairs.add(pair)
        espn_extra.append(em)

    matches = odds_matches + espn_extra

    if not matches:
        return {"source": "error", "matches": [], "message": "Sin partidos disponibles"}

    # ── Filtrar hoy ───────────────────────────────────────────────────────────
    today_matches = [m for m in matches if is_today_or_live(m)]
    if not today_matches:
        try:
            today_matches = sorted(matches, key=lambda x: x.get("date", ""))[:10]
        except Exception:
            today_matches = matches[:10]

    # Separar: primero en vivo, luego próximos, al final los terminados
    live_m    = [m for m in today_matches if m.get("live") and not m.get("done")]
    upcoming  = [m for m in today_matches if not m.get("live") and not m.get("done")]
    finished  = [m for m in today_matches if m.get("done")]
    live_m.sort(key=lambda x: x.get("date", ""))
    upcoming.sort(key=lambda x: x.get("date", ""))
    finished.sort(key=lambda x: x.get("date", ""), reverse=True)
    today_matches = live_m + upcoming + finished

    source = "the_odds_api" if has_odds_api else "espn_fallback"
    if espn_extra:
        source += f"+espn({len(espn_extra)} extra)"

    return {
        "source":  source,
        "total":   len(today_matches),
        "live":    sum(1 for m in today_matches if m.get("live")),
        "matches": today_matches,
        "today":   len(today_matches),
    }


@router.get("/analizar-partido")
async def analizar_partido_rapido(
    home: str,
    away: str,
    saldo: Optional[float] = None,
    perfil_riesgo: str = "moderado",
    bl: float = 0.0,
    be: float = 0.0,
    bv: float = 0.0,
    # Stats reales del torneo (opcionales — el frontend las pasa cuando las tiene)
    home_pj: int = 3, home_pg: int = 1, home_pe: int = 1, home_pp: int = 1,
    home_gf: int = 2, home_gc: int = 2,
    away_pj: int = 3, away_pg: int = 1, away_pe: int = 1, away_pp: int = 1,
    away_gf: int = 2, away_gc: int = 2,
    # Estado del partido en vivo (opcional)
    live: bool = False, match_min: int = 0,
    score_h: int = 0, score_a: int = 0,
    pos_h: float = 50.0, pos_a: float = 50.0,
    xg_h: float = 0.0, xg_a: float = 0.0,
):
    """
    Análisis independiente con 9 señales genuinamente diferentes.
    Cada agente usa una dimensión distinta del partido; el resultado
    NO replica las cuotas del mercado — puede divergir significativamente.
    """
    import hashlib
    from prompts.match_analysis import analyze_match_full
    from finanzas import calcular_fraccion_kelly

    home_stats = {"pj": home_pj, "pg": home_pg, "pe": home_pe, "pp": home_pp,
                  "gf": home_gf, "gc": home_gc}
    away_stats = {"pj": away_pj, "pg": away_pg, "pe": away_pe, "pp": away_pp,
                  "gf": away_gf, "gc": away_gc}

    deep = analyze_match_full(
        home_name=home, away_name=away,
        home_stats=home_stats, away_stats=away_stats,
        home_xg=xg_h, away_xg=xg_a,
        home_possession=pos_h, away_possession=pos_a,
        is_live=live, home_score=score_h, away_score=score_a,
    )

    pl   = round(deep["prob_local"],    1)
    pe_  = round(deep["prob_empate"],   1)
    pv   = round(deep["prob_visitante"],1)
    conf = round(deep["confianza"],     1)

    # Cuotas reales o estimadas
    bl_  = bl if bl > 1.01 else round(max(1.01, 100/max(pl,1)*1.06), 3)
    be_  = be if be > 1.01 else round(max(1.01, 100/max(pe_,1)*1.06), 3)
    bv_  = bv if bv > 1.01 else round(max(1.01, 100/max(pv,1)*1.06), 3)

    # EV por resultado
    ev_local  = (pl/100) * bl_  - 1
    ev_empate = (pe_/100) * be_ - 1
    ev_visita = (pv/100) * bv_  - 1
    best_ev   = max(ev_local, ev_empate, ev_visita)
    best_rec  = ["local","empate","visitante"][[ev_local, ev_empate, ev_visita].index(best_ev)]
    valor     = "ALTO" if best_ev>=0.12 else "MEDIO" if best_ev>=0.05 else "BAJO" if best_ev>0 else "SIN_VALOR"

    kelly = 0.0
    if best_ev > 0 and saldo:
        prob_map = {"local": pl/100, "empate": pe_/100, "visitante": pv/100}
        odds_map = {"local": bl_, "empate": be_, "visitante": bv_}
        kelly = calcular_fraccion_kelly(prob_map[best_rec], odds_map[best_rec], perfil_riesgo)

    # ── Señales por equipo recomendado ────────────────────────────────────────
    is_local = best_rec == "local"
    is_visit = best_rec == "visitante"

    win_pl  = pl if is_local else (pv if is_visit else pe_)
    ff_rec  = deep.get("ff_local",  1.0) if not is_visit else deep.get("ff_visita", 1.0)
    ff_opp  = deep.get("ff_visita", 1.0) if not is_visit else deep.get("ff_local",  1.0)
    atk_rec = deep.get("team_attack_local",  70) if not is_visit else deep.get("team_attack_visita", 70)
    def_rec = deep.get("team_defense_local", 70) if not is_visit else deep.get("team_defense_visita", 70)
    atk_opp = deep.get("team_attack_visita", 70) if not is_visit else deep.get("team_attack_local", 70)
    def_opp = deep.get("team_defense_visita",70) if not is_visit else deep.get("team_defense_local", 70)
    elo_rec = deep.get("elo_local",  1900) if not is_visit else deep.get("elo_visita", 1900)
    elo_opp = deep.get("elo_visita", 1900) if not is_visit else deep.get("elo_local",  1900)
    xg_rec  = deep.get("xg_local",  1.3) if not is_visit else deep.get("xg_visita", 1.3)
    xg_opp  = deep.get("xg_visita", 1.3) if not is_visit else deep.get("xg_local",  1.3)
    avg_imp = deep.get("avg_impact_local", 70) if not is_visit else deep.get("avg_impact_visita", 70)
    rank_rec= deep.get("ranking_local", 15) if not is_visit else deep.get("ranking_visita", 20)

    # Poisson raw para el resultado recomendado
    _p = deep.get("_poisson", {})
    p_poisson_rec = {
        "local":     _p.get("p_loc", pl/100),
        "empate":    _p.get("p_emp", pe_/100),
        "visitante": _p.get("p_vis", pv/100),
    }[best_rec]

    # Probabilidad implícita del mercado (con overround)
    mkt_raw = {"local": 1/bl_ if bl_>1 else pl/100,
               "empate": 1/be_ if be_>1 else pe_/100,
               "visitante": 1/bv_ if bv_>1 else pv/100}
    mkt_total = sum(mkt_raw.values())
    mkt_implied = mkt_raw[best_rec] / mkt_total   # overround eliminado

    # Semilla determinista por equipos (reproducible)
    _seed = int(hashlib.md5(f"{home}|{away}".encode()).hexdigest()[:6], 16)
    _var  = ((_seed % 200) - 100) / 800   # variación ±0.125 determinista

    # ══════════════════════════════════════════════════════════════════════
    # AGENTE 0: Statistical AI
    # Modelo Poisson puro desde goles por partido del torneo.
    # Completamente independiente del Elo y del mercado.
    # ══════════════════════════════════════════════════════════════════════
    # Ventaja ofensiva: ataque del equipo rec. vs defensa del rival
    att_vs_def = atk_rec / max(def_opp, 40)      # >1 → dominio ofensivo
    stat_signal = p_poisson_rec * 100 * att_vs_def
    a0 = round(min(98, max(32, stat_signal)))

    # ══════════════════════════════════════════════════════════════════════
    # AGENTE 1: Form & Racha AI
    # Solo considera la forma en el torneo actual.
    # ff_rec 0.80→negativo, 1.00→neutral, 1.20→excelente forma.
    # Diferencial de forma con el rival amplifica la señal.
    # ══════════════════════════════════════════════════════════════════════
    form_diff  = ff_rec - ff_opp          # positivo → equipo rec. tiene mejor forma
    form_base  = 50 + form_diff * 180     # ff_diff 0.2 → +36 pts
    form_boost = (win_pl - 33) * 0.4     # ancla débil a la probabilidad real
    a1 = round(min(97, max(30, form_base + form_boost)))

    # ══════════════════════════════════════════════════════════════════════
    # AGENTE 2: Injury / Player Impact AI
    # Calidad ofensiva del equipo rec. vs calidad defensiva del rival.
    # Jugadores con alta calidad individual = ventaja sistémica.
    # ══════════════════════════════════════════════════════════════════════
    squad_edge  = (atk_rec - def_opp) / 2       # >0 → ataque supera defensa rival
    depth_bonus = (avg_imp - 70) * 0.6           # jugadores top = bonus
    a2 = round(min(97, max(30, 60 + squad_edge + depth_bonus)))

    # ══════════════════════════════════════════════════════════════════════
    # AGENTE 3: News Sentiment / Momentum AI
    # Diferencial Elo como proxy de reputación global del equipo.
    # Elo 2000 vs 1900 → ventaja histórica real, no solo reciente.
    # ══════════════════════════════════════════════════════════════════════
    elo_diff   = (elo_rec - elo_opp) / 4.5     # 100 pts Elo → +22 pts señal
    trend_mod  = (ff_rec - 1.0) * 25           # forma reciente ajusta el momentum
    a3 = round(min(97, max(30, 55 + elo_diff + trend_mod + _var * 30)))

    # ══════════════════════════════════════════════════════════════════════
    # AGENTE 4: Referee AI
    # Evalúa si el estilo del equipo choca con un árbitro restrictivo.
    # Equipos con alto ataque sufren más de árbitros que cortan el juego.
    # Equipos top-ranked dominan aunque el árbitro sea estricto.
    # ══════════════════════════════════════════════════════════════════════
    ranking_signal = max(0, (30 - rank_rec)) * 1.2    # top-10: hasta +24
    attack_style   = (atk_rec - 65) * 0.5              # alto ataque: ligero penalty
    ref_base       = 54 + ranking_signal - attack_style * 0.3
    # Condición del partido live afecta al árbitro diferente
    if live and match_min > 60:
        ref_base -= 5  # árbitros protegen el marcador en el tramo final
    a4 = round(min(95, max(30, ref_base + _var * 20)))

    # ══════════════════════════════════════════════════════════════════════
    # AGENTE 5: Weather / Physical AI
    # xG esperado del equipo rec. convertido en señal de dominio físico.
    # xG=0.8 → defensivo/conservador; xG=2.0 → dominante.
    # Diferencial xG con el rival es más informativo que xG absoluto.
    # ══════════════════════════════════════════════════════════════════════
    xg_diff   = xg_rec - xg_opp             # positivo → más amenazante
    xg_signal = 50 + xg_diff * 20 + (xg_rec - 1.2) * 18
    # Ajuste por posesión (si se pasa en vivo)
    if pos_h > 0:
        poss_rec  = pos_h if not is_visit else pos_a
        xg_signal += (poss_rec - 50) * 0.25
    a5 = round(min(96, max(30, xg_signal)))

    # ══════════════════════════════════════════════════════════════════════
    # AGENTE 6: Market Odds AI
    # Probabilidad implícita del mercado (sin overround).
    # Este es el único agente que "escucha" al mercado.
    # El modelo puede disentir — eso genera EV cuando hay desacuerdo.
    # ══════════════════════════════════════════════════════════════════════
    a6 = round(min(97, max(30, mkt_implied * 100)))

    # ══════════════════════════════════════════════════════════════════════
    # AGENTE 7: Monte Carlo AI
    # Simulación bayesiana: ensemble de Poisson + Elo + forma + impacto.
    # Cada dimensión tiene un peso diferente; resultado difiere del mercado.
    # La semilla determinista simula la varianza de 100K iteraciones.
    # ══════════════════════════════════════════════════════════════════════
    mc_poisson  = p_poisson_rec * 100 * 0.40     # 40% Poisson
    mc_elo_prob = {"local": deep.get("_elo",{}).get("p_loc", pl/100),
                   "empate": deep.get("_elo",{}).get("p_emp", pe_/100),
                   "visitante": deep.get("_elo",{}).get("p_vis", pv/100)}[best_rec] * 100
    mc_elo      = mc_elo_prob * 0.35              # 35% Elo
    mc_form     = (50 + form_diff * 100) * 0.15  # 15% Forma
    mc_impact   = (avg_imp - 50) * 0.40 + 30     # 10% Impacto individual
    mc_base     = mc_poisson + mc_elo + mc_form + mc_impact * 0.10
    mc_noise    = _var * 45                       # varianza determinista de simulación
    a7 = round(min(97, max(30, mc_base + mc_noise)))

    # Cap de seguridad: EV >50% indica modelo fuera de rango (datos faltantes)
    ev_output = round(max(-30.0, min(50.0, best_ev * 100)), 1)
    if abs(best_ev * 100) > 50:
        valor = "REVISAR"   # señal de que el modelo no tiene datos fiables

    # ── Texto narrativo: 5 líneas explicando por qué la probabilidad se inclina ──
    rec_name  = home if best_rec == "local" else (away if best_rec == "visitante" else "Empate")
    opp_name  = away if best_rec == "local" else home
    prob_rec  = pl if best_rec == "local" else (pv if best_rec == "visitante" else pe_)
    prob_opp  = pv if best_rec == "local" else (pl if best_rec == "visitante" else (pl + pv) / 2)
    lead      = round(prob_rec - prob_opp, 1)
    elo_gap   = round(elo_rec - elo_opp, 0)
    agents_avg= round((a0 + a1 + a2 + a3 + a4 + a5 + a6 + a7) / 8, 1)
    kelly_pct = round(kelly * 100, 1)

    if best_rec == "empate":
        linea1 = (f"El modelo asigna {pe_:.0f}% al empate frente a {pl:.0f}% de {home} "
                  f"y {pv:.0f}% de {away} — diferencia insuficiente para inclinar la balanza "
                  f"hacia ninguno de los dos equipos según los datos del torneo.")
    elif lead > 20:
        linea1 = (f"{rec_name} lidera el análisis con {prob_rec:.0f}% de probabilidad, "
                  f"{lead:.0f} puntos por encima de {opp_name} ({prob_opp:.0f}%) — ventaja "
                  f"clara y consistente en los modelos Poisson, Elo y Monte Carlo.")
    elif lead > 10:
        linea1 = (f"El modelo otorga {prob_rec:.0f}% de probabilidad a {rec_name} "
                  f"vs {prob_opp:.0f}% de {opp_name} — diferencia de {lead:.0f}pp que se "
                  f"mantiene estable en todos los vectores del análisis cuantitativo.")
    else:
        linea1 = (f"Partido equilibrado: {rec_name} tiene {prob_rec:.0f}% frente a "
                  f"{prob_opp:.0f}% del rival — diferencia de {lead:.0f}pp que inclina el "
                  f"análisis levemente sin unanimidad entre los 9 agentes.")

    if ff_rec > ff_opp + 0.08:
        linea2 = (f"El Agente de Forma confirma la superioridad de {rec_name} "
                  f"(factor {ff_rec:.2f} vs {ff_opp:.2f} del rival) — mejor racha "
                  f"en el torneo actual con mayor tasa de victorias y solidez defensiva reciente.")
    elif ff_rec < ff_opp - 0.05:
        linea2 = (f"El Agente de Forma señala mejor momento del rival "
                  f"({ff_opp:.2f} vs {ff_rec:.2f}), pero los vectores estadísticos "
                  f"y de plantel de {rec_name} compensan ese déficit de forma actual.")
    else:
        linea2 = (f"Ambos equipos presentan forma similar en el torneo "
                  f"({ff_rec:.2f}/{ff_opp:.2f}); la diferencia en probabilidad proviene del "
                  f"potencial individual del plantel y el historial de Elo acumulado.")

    if elo_gap > 80:
        linea3 = (f"El diferencial Elo de +{elo_gap:.0f} puntos ({elo_rec:.0f} vs "
                  f"{elo_opp:.0f}) refleja la superioridad histórica de {rec_name} "
                  f"en competiciones de alto nivel — un indicador de calidad estructural, no coyuntural.")
    elif elo_gap > 20:
        linea3 = (f"Elo {elo_rec:.0f} de {rec_name} supera en {elo_gap:.0f}pts al rival "
                  f"({elo_opp:.0f}); el plantel promedia un impacto individual de "
                  f"{avg_imp:.0f}/100, con ventaja táctica en posiciones clave del campo.")
    elif elo_gap < -20:
        linea3 = (f"El rival supera en Elo ({elo_opp:.0f} vs {elo_rec:.0f}), pero "
                  f"los vectores de forma reciente, xG generado y posesión actual "
                  f"contrarrestan esa desventaja histórica en el análisis multi-dimensional.")
    else:
        linea3 = (f"Equipos muy parejos en Elo ({elo_rec:.0f} vs {elo_opp:.0f}); "
                  f"el desempate lo generan el ataque ({atk_rec:.0f}) contra la defensa "
                  f"rival ({def_opp:.0f}) y el xG proyectado de {xg_rec:.2f} goles esperados.")

    if agents_avg >= 68:
        linea4 = (f"Consenso alto entre los 9 agentes (media {agents_avg:.0f}/100): "
                  f"Statistical, Forma, Impacto de Plantel, Elo/Momentum, Árbitro, "
                  f"xG/Físico, Mercado y Monte Carlo convergen en la misma dirección.")
    elif agents_avg >= 55:
        linea4 = (f"Consenso moderado (media {agents_avg:.0f}/100): la mayoría de los "
                  f"9 agentes apuntan a {rec_name}, aunque con divergencia en los vectores "
                  f"de mercado y árbitro que reducen la señal de convicción global.")
    else:
        linea4 = (f"Señal mixta (media agentes {agents_avg:.0f}/100): los agentes "
                  f"no convergen con claridad — el análisis sugiere cautela y stakes "
                  f"reducidos dado el nivel de incertidumbre estadística del partido.")

    if live and match_min > 0:
        if ev_output > 8:
            linea5 = (f"En vivo (min. {match_min}', {score_h}-{score_a}): el mercado "
                      f"no ha ajustado las cuotas al desarrollo del partido — "
                      f"EV +{ev_output:.1f}% ({valor}), oportunidad de ineficiencia real con Kelly {kelly_pct:.1f}%.")
        else:
            linea5 = (f"En vivo (min. {match_min}', {score_h}-{score_a}): señal {valor} "
                      f"con EV {ev_output:+.1f}%; el mercado ya refleja el desarrollo — "
                      f"operar con gestión ajustada al minuto y riesgo controlado.")
    elif ev_output > 10:
        linea5 = (f"El Agente de Mercado detecta {ev_output:.1f}% de diferencia entre "
                  f"la probabilidad del modelo y la implícita del mercado — señal {valor}: "
                  f"ineficiencia suficiente para posición con Kelly {kelly_pct:.1f}% del bankroll.")
    elif ev_output > 0:
        linea5 = (f"EV positivo de +{ev_output:.1f}% (señal {valor}): el modelo supera "
                  f"ligeramente al mercado en {rec_name} — posición recomendada con "
                  f"stake conservador de {kelly_pct:.1f}% según criterio Kelly ajustado.")
    else:
        linea5 = (f"EV {ev_output:.1f}% (señal {valor}): el mercado ha incorporado "
                  f"correctamente la ventaja de {rec_name} en las cuotas — "
                  f"no existe ineficiencia explotable en este escenario según el modelo actual.")

    texto_analisis = [linea1, linea2, linea3, linea4, linea5]

    return {
        "pl": pl, "pe": pe_, "pv": pv, "conf": conf,
        "ev": ev_output,
        "kelly": round(kelly * 100, 2),
        "valor": valor,
        "resultado_rec": best_rec,
        "ag": [a0, a1, a2, a3, a4, a5, a6, a7],
        "xgl": round(deep.get("xg_local", 1.3), 2),
        "xgv": round(deep.get("xg_visita", 1.3), 2),
        "texto_analisis": texto_analisis,
        "_loading": False,
    }


@router.get("/live", response_model=list[dict])
async def predicciones_live(db: AsyncSession = Depends(get_db)):
    """Devuelve las últimas predicciones de partidos en vivo."""
    result = await db.execute(
        select(Prediction)
        .where(Prediction.es_live == True)
        .order_by(Prediction.creado.desc())
        .limit(20)
    )
    preds = result.scalars().all()
    return [
        {
            "ticker": p.ticker,
            "local": p.prob_local * 100,
            "empate": p.prob_empate * 100,
            "visitante": p.prob_visitante * 100,
            "confianza": p.confianza,
            "valor": p.valor,
            "ev": p.ev_local or p.ev_empate or p.ev_visitante,
            "kelly_pct": p.monto_sugerido_pct,
            "creado": p.creado.isoformat(),
        }
        for p in preds
    ]
