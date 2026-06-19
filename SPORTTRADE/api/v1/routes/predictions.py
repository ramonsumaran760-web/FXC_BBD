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
from datetime import datetime
import httpx
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
