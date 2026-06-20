"""
match_analysis.py — Pipeline estadístico completo para análisis de partidos.

SIN LLM externo — usa modelos matemáticos estándar de la industria:
  • Poisson distribution (modelo estándar en sports betting)
  • Dixon-Coles correction (sesgo en marcadores bajos)
  • Elo rating por ranking FIFA
  • Form factor por resultados recientes en el torneo
  • Player Impact Matrix por jugador individual
"""
from __future__ import annotations
import math
import logging
from typing import Optional

from prompts.world_cup_squads import get_squad, SQUADS

logger = logging.getLogger("fxcbbd.analysis")


# ── CONSTANTES DEL MODELO ─────────────────────────────────────────────────────

# Goles promedio en fase de grupos del Mundial (histórico FIFA 2014-2022)
AVG_GOALS_WORLD_CUP = 2.72
HOME_ADVANTAGE_WC   = 1.08   # ventaja sede en mundiales (menor que liga doméstica)
MAX_GOALS_SIM       = 8      # máximo goles a simular en distribución Poisson


# ── 1. ELO POR RANKING FIFA ───────────────────────────────────────────────────

def ranking_to_elo(ranking: int) -> float:
    """
    Convierte ranking FIFA a puntuación Elo.
    Rango: ~2050 (ranking 1) → ~1000 (ranking 200).
    """
    return max(1000.0, 2050.0 - (ranking - 1) * 5.5)


def elo_win_probability(elo_home: float, elo_away: float) -> tuple[float, float, float]:
    """
    Calcula P(local), P(empate), P(visita) basado en diferencia Elo.
    Usa el modelo estándar de soccer Elo con factor de empate.
    """
    diff = elo_home - elo_away
    # Probabilidad de victoria local esperada (fórmula Elo)
    exp_home = 1 / (1 + 10 ** (-diff / 400))

    # Calibración para fútbol (empates más comunes que en otros deportes)
    # Distribución promedio mundial: 46% L / 24% E / 30% V
    draw_factor = 0.22 + max(0, 0.08 * (1 - abs(diff) / 300))
    p_local     = max(0.05, exp_home - draw_factor * 0.5)
    p_visita    = max(0.05, (1 - exp_home) - draw_factor * 0.5)
    p_empate    = max(0.05, 1 - p_local - p_visita)

    # Renormalizar
    total = p_local + p_empate + p_visita
    return p_local / total, p_empate / total, p_visita / total


# ── 2. FORM FACTOR ────────────────────────────────────────────────────────────

def form_factor(pg: int, pe: int, pp: int, gf: int, gc: int, pj: int) -> float:
    """
    Calcula factor de forma del torneo [0.80 – 1.20].
    Basado en puntos/partido y diferencia de goles.
    """
    if pj == 0:
        return 1.0
    puntos_pp = ((pg * 3 + pe * 1) / pj) / 3.0   # normalizado [0-1]
    dif_goles  = (gf - gc) / max(pj, 1)
    # Factor entre 0.80 y 1.20
    return max(0.80, min(1.20, 0.90 + puntos_pp * 0.20 + dif_goles * 0.025))


# ── 3. POISSON DISTRIBUTION ───────────────────────────────────────────────────

def poisson_pmf(k: int, lam: float) -> float:
    """P(X = k) donde X ~ Poisson(lambda)."""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return (lam ** k * math.exp(-lam)) / math.factorial(k)


def dixon_coles_rho(home_goals: int, away_goals: int, lam: float, mu: float) -> float:
    """
    Corrección Dixon-Coles para marcadores bajos (0-0, 1-0, 0-1, 1-1).
    rho calibrado para fútbol = -0.13.
    """
    rho = -0.13
    if home_goals == 0 and away_goals == 0:
        return 1 - lam * mu * rho
    elif home_goals == 1 and away_goals == 0:
        return 1 + mu * rho
    elif home_goals == 0 and away_goals == 1:
        return 1 + lam * rho
    elif home_goals == 1 and away_goals == 1:
        return 1 - rho
    return 1.0


def poisson_match_probs(
    xg_home: float,
    xg_away: float,
    n: int = MAX_GOALS_SIM,
) -> tuple[float, float, float]:
    """
    Calcula P(local_win), P(empate), P(visita_win) usando distribución Poisson
    con corrección Dixon-Coles para marcadores bajos.
    """
    p_local  = 0.0
    p_empate = 0.0
    p_visita = 0.0

    for i in range(n + 1):
        for j in range(n + 1):
            prob = (
                poisson_pmf(i, xg_home)
                * poisson_pmf(j, xg_away)
                * dixon_coles_rho(i, j, xg_home, xg_away)
            )
            if i > j:
                p_local  += prob
            elif i == j:
                p_empate += prob
            else:
                p_visita += prob

    total = p_local + p_empate + p_visita
    if total == 0:
        return 0.40, 0.28, 0.32
    return p_local / total, p_empate / total, p_visita / total


# ── 4. PLAYER IMPACT MATRIX ───────────────────────────────────────────────────

def analyze_players(
    squad: dict,
    goles_wc: int = 0,
    asists_wc: int = 0,
) -> dict:
    """
    Analiza jugadores del equipo y calcula su impacto individual.
    goles_wc / asists_wc: estadísticas reales del torneo si están disponibles.

    Retorna:
    - jugadores: lista con impacto individual calculado
    - team_attack_rating: fortaleza ofensiva 0-100
    - team_defense_rating: fortaleza defensiva 0-100
    - top_player: jugador de mayor impacto
    - avg_impact: impacto promedio del equipo
    """
    if not squad:
        return {"jugadores": [], "team_attack_rating": 60, "team_defense_rating": 60,
                "top_player": None, "avg_impact": 60}

    players = squad.get("jugadores", [])
    analyzed = []
    attackers  = []
    defenders  = []

    for p in players:
        base    = p.get("impacto", 70)
        pos     = p.get("pos", "CM")
        age     = p.get("edad", 27)
        name    = p.get("nombre", "")

        # Penalización/bonus por edad
        if age < 20:
            age_mod = -3
        elif age < 22:
            age_mod = 0
        elif age <= 29:
            age_mod = +3
        elif age <= 32:
            age_mod = 0
        elif age <= 35:
            age_mod = -5
        else:
            age_mod = -12

        # Bonus por goles/asistencias en el torneo (jugadores clave del squad principal)
        wc_mod = 0
        if goles_wc > 0 and pos in ("ST", "FWD", "CAM", "LW", "RW"):
            wc_mod += min(8, goles_wc * 2)
        if asists_wc > 0 and pos in ("CAM", "LW", "RW", "CM"):
            wc_mod += min(4, asists_wc)

        final_impact = max(40, min(100, base + age_mod + wc_mod))

        entry = {
            "nombre":    name,
            "pos":       pos,
            "edad":      age,
            "dorsal":    p.get("dorsal", 0),
            "impacto":   final_impact,
            "forma":     "alta" if final_impact >= 85 else "media" if final_impact >= 70 else "baja",
            "rol":       "clave" if final_impact >= 85 else "titular" if final_impact >= 72 else "reserva",
        }
        analyzed.append(entry)

        if pos in ("ST", "FWD", "CAM", "LW", "RW"):
            attackers.append(final_impact)
        elif pos in ("CB", "LB", "RB", "GK", "DM"):
            defenders.append(final_impact)

    top_player = max(analyzed, key=lambda x: x["impacto"], default=None)
    team_attack  = round(sum(attackers) / len(attackers)) if attackers else 65
    team_defense = round(sum(defenders) / len(defenders)) if defenders else 65
    avg_impact   = round(sum(p["impacto"] for p in analyzed) / len(analyzed)) if analyzed else 65

    return {
        "jugadores":           sorted(analyzed, key=lambda x: -x["impacto"])[:7],
        "team_attack_rating":  min(100, team_attack),
        "team_defense_rating": min(100, team_defense),
        "top_player":          top_player,
        "avg_impact":          avg_impact,
    }


# ── 5. PIPELINE PRINCIPAL ─────────────────────────────────────────────────────

def analyze_match_full(
    home_name: str,
    away_name: str,
    home_stats: dict,   # {pj, pg, pe, pp, gf, gc} de standings ESPN
    away_stats: dict,
    home_xg: float = 0.0,    # xG en vivo del partido (si disponible)
    away_xg: float = 0.0,
    home_possession: float = 50.0,
    away_possession: float = 50.0,
    is_live: bool = False,
    home_score: int = 0,
    away_score: int = 0,
) -> dict:
    """
    Análisis estadístico completo sin LLM.

    Pipeline:
    1. Elo por ranking FIFA del squad → fortaleza base
    2. Form factor por resultados en el torneo
    3. Player Impact Matrix → fortaleza individual
    4. xG esperado ajustado (Poisson input)
    5. Distribución Poisson con Dixon-Coles → probabilidades exactas
    6. Ajuste live si partido en curso (marcador actual)
    7. Output estructurado con análisis por jugador
    """

    # ── Paso 1: Squad data y Elo ─────────────────────────────────────────────
    home_squad = get_squad(home_name)
    away_squad = get_squad(away_name)

    home_ranking = home_squad.get("ranking_fifa", 15) if home_squad else 15
    away_ranking = away_squad.get("ranking_fifa", 20) if away_squad else 20

    elo_home = ranking_to_elo(home_ranking)
    elo_away = ranking_to_elo(away_ranking)

    # ── Paso 2: Form factor del torneo ────────────────────────────────────────
    h = home_stats
    v = away_stats
    ff_home = form_factor(h.get("pg",1), h.get("pe",1), h.get("pp",1),
                           h.get("gf",2), h.get("gc",2), h.get("pj",3))
    ff_away = form_factor(v.get("pg",1), v.get("pe",1), v.get("pp",1),
                           v.get("gf",2), v.get("gc",2), v.get("pj",3))

    # ── Paso 3: Player Impact Matrix ─────────────────────────────────────────
    home_players = analyze_players(home_squad)
    away_players = analyze_players(away_squad)

    # Player factor: equipos con más impacto atacante marcaron más
    home_player_factor = home_players["team_attack_rating"] / 75.0
    away_player_factor = away_players["team_attack_rating"] / 75.0

    # ── Paso 4: xG esperado ──────────────────────────────────────────────────
    # Si hay datos en vivo, usarlos; si no, calcular desde histórico del torneo
    if home_xg > 0 and away_xg > 0:
        lambda_home = home_xg * home_player_factor * ff_home * HOME_ADVANTAGE_WC
        lambda_away = away_xg * away_player_factor * ff_away
    else:
        # Estimar xG desde goles por partido × factor forma × impacto
        gpp_home = h.get("gf", 2) / max(h.get("pj", 3), 1)
        gpp_away = v.get("gf", 2) / max(v.get("pj", 3), 1)
        # Ajuste defensivo cruzado: el ataque local vs la defensa visitante
        def_factor_away = max(0.7, 1.0 - (v.get("gc",2)/max(v.get("pj",3),1) - 1.0) * 0.1)
        def_factor_home = max(0.7, 1.0 - (h.get("gc",2)/max(h.get("pj",3),1) - 1.0) * 0.1)
        lambda_home = gpp_home * ff_home * home_player_factor * HOME_ADVANTAGE_WC * def_factor_away
        lambda_away = gpp_away * ff_away * away_player_factor * def_factor_home

    # Clamp razonable
    lambda_home = max(0.3, min(4.5, lambda_home))
    lambda_away = max(0.3, min(4.5, lambda_away))

    # ── Paso 5: Poisson + Dixon-Coles ────────────────────────────────────────
    p_loc_poisson, p_emp_poisson, p_vis_poisson = poisson_match_probs(lambda_home, lambda_away)

    # ── Paso 6: Elo puro (como referencia / agente 2) ────────────────────────
    p_loc_elo, p_emp_elo, p_vis_elo = elo_win_probability(elo_home, elo_away)

    # ── Paso 7: Ensemble (Poisson 70% + Elo 30%) ─────────────────────────────
    p_loc  = p_loc_poisson  * 0.70 + p_loc_elo  * 0.30
    p_emp  = p_emp_poisson  * 0.70 + p_emp_elo  * 0.30
    p_vis  = p_vis_poisson  * 0.70 + p_vis_elo  * 0.30

    # ── Paso 8: Ajuste live por marcador actual ───────────────────────────────
    if is_live and (home_score != 0 or away_score != 0):
        diff = home_score - away_score
        # Cada gol de diferencia desplaza ~8% la probabilidad
        adj = diff * 0.08
        p_loc  = max(0.03, p_loc  + adj)
        p_vis  = max(0.03, p_vis  - adj)
        p_emp  = max(0.03, p_emp  - abs(adj) * 0.3)
        total  = p_loc + p_emp + p_vis
        p_loc /= total; p_emp /= total; p_vis /= total

    # ── Paso 9: Confianza del modelo ─────────────────────────────────────────
    # Mayor confianza cuando hay más partidos jugados Y los modelos coinciden.
    # Con 3 partidos por equipo (6 total / 12 necesarios) → calidad 0.50 → conf ~65%.
    # Con 5 partidos por equipo (10 total) → calidad 0.83 → conf ~80%.
    # Solo supera 85% con datos de torneo completos + alta concordancia inter-modelo.
    total_pj     = h.get("pj", 0) + v.get("pj", 0)
    data_quality = min(1.0, total_pj / 12)                    # necesita 6 partidos por equipo
    agreement    = max(0.0, 1 - abs(p_loc_poisson - p_loc_elo) * 2.5)  # penaliza desacuerdo
    squad_bonus  = min(0.08, (home_players["avg_impact"] + away_players["avg_impact"]) / 2800)
    confianza    = max(0.35, min(0.88,
        data_quality * 0.42 + agreement * 0.32 + 0.18 + squad_bonus
    ))

    # ── Paso 10: Player ratings individuales en formato para el frontend ──────
    # Impacto individual de top jugadores (0-100)
    top_home = home_players["jugadores"][:6]
    top_away = away_players["jugadores"][:6]

    return {
        # Probabilidades finales
        "prob_local":     round(p_loc * 100, 1),
        "prob_empate":    round(p_emp * 100, 1),
        "prob_visitante": round(p_vis * 100, 1),
        "confianza":      round(confianza * 100, 1),

        # xG calculados
        "xg_local":   round(lambda_home, 2),
        "xg_visita":  round(lambda_away, 2),

        # Elo / ratings de equipo
        "elo_local":  round(elo_home),
        "elo_visita": round(elo_away),
        "ff_local":   round(ff_home, 3),
        "ff_visita":  round(ff_away, 3),
        "ranking_local":  home_ranking,
        "ranking_visita": away_ranking,

        # Player Impact Matrix
        "jugadores_local": top_home,
        "jugadores_visita": top_away,
        "team_attack_local":   home_players["team_attack_rating"],
        "team_attack_visita":  away_players["team_attack_rating"],
        "team_defense_local":  home_players["team_defense_rating"],
        "team_defense_visita": away_players["team_defense_rating"],
        "top_player_local":  home_players["top_player"],
        "top_player_visita": away_players["top_player"],
        "avg_impact_local":  home_players["avg_impact"],
        "avg_impact_visita": away_players["avg_impact"],

        # Estilo e info del squad
        "estilo_local":     home_squad.get("estilo", "") if home_squad else "",
        "estilo_visita":    away_squad.get("estilo", "") if away_squad else "",
        "fortaleza_local":  home_squad.get("fortaleza", "") if home_squad else "",
        "fortaleza_visita": away_squad.get("fortaleza", "") if away_squad else "",
        "debilidad_local":  home_squad.get("debilidad", "") if home_squad else "",
        "debilidad_visita": away_squad.get("debilidad", "") if away_squad else "",
        "entrenador_local": home_squad.get("entrenador", "") if home_squad else "",
        "entrenador_visita":away_squad.get("entrenador", "") if away_squad else "",

        # Debug interno
        "_poisson": {
            "lambda_home": round(lambda_home, 3),
            "lambda_away": round(lambda_away, 3),
            "p_loc": round(p_loc_poisson, 4),
            "p_emp": round(p_emp_poisson, 4),
            "p_vis": round(p_vis_poisson, 4),
        },
        "_elo": {
            "elo_home": round(elo_home),
            "elo_away": round(elo_away),
            "p_loc": round(p_loc_elo, 4),
            "p_emp": round(p_emp_elo, 4),
            "p_vis": round(p_vis_elo, 4),
        },
    }
