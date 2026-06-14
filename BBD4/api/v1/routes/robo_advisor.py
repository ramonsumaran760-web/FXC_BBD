"""
Robo-Advisor routes — análisis IA con Claude + historial
"""
import json
from typing import Optional
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.security import get_current_user
from core.rate_limit import limiter, get_limit
from core.config import settings
from models.models import Usuario, PosicionPortafolio, AnalisisRoboAdvisor, Alerta
from services.services import robo_advisor_analizar
from services.notification_service import email_alerta_riesgo

router = APIRouter(prefix="/robo-advisor", tags=["robo-advisor"])


class RoboAdvisorSchema(BaseModel):
    edad: Optional[int] = None
    ingresos_anuales_usd: Optional[float] = None
    tolerancia_riesgo: Optional[str] = None


@router.post("")
@limiter.limit(get_limit("robo_advisor"))
async def robo_advisor(request: Request, data: RoboAdvisorSchema,
                       current_user: Usuario = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    perfil_dict = {
        "id": current_user.id,
        "edad": data.edad or current_user.edad or 30,
        "ingresos_anuales_usd": data.ingresos_anuales_usd or current_user.ingresos_anuales_usd or 15000,
        "tolerancia_riesgo": data.tolerancia_riesgo or current_user.tolerancia_riesgo or "moderada",
        "saldo_usd": current_user.saldo_usd
    }

    pos_res = await db.execute(select(PosicionPortafolio).where(
        PosicionPortafolio.usuario_id == current_user.id,
        PosicionPortafolio.acciones > 0))
    posiciones = [p.to_dict() for p in pos_res.scalars().all()]

    resultado = robo_advisor_analizar(perfil_dict, posiciones, settings.CLAUDE_API_KEY)

    analisis = AnalisisRoboAdvisor(
        usuario_id=current_user.id,
        perfil=resultado["perfil"],
        score_riesgo=resultado["score_riesgo"],
        alerta_riesgo=resultado["alerta_riesgo"],
        concentracion_max_ticker=resultado.get("concentracion_max_ticker"),
        concentracion_max_pct=resultado.get("concentracion_max_pct"),
        sugerencia_rebalanceo=resultado.get("sugerencia_rebalanceo"),
        acciones_recomendadas=json.dumps(resultado.get("acciones_recomendadas", [])),
        explicacion_voz=resultado.get("explicacion_voz"),
        prompt_json_enviado=json.dumps(resultado.get("_prompt_json_enviado", {})),
        respuesta_json=json.dumps(resultado),
        modelo_ia=resultado.get("_modelo", "local")
    )
    db.add(analisis)

    # Actualizar perfil usuario
    if data.tolerancia_riesgo:
        current_user.tolerancia_riesgo = data.tolerancia_riesgo
    current_user.perfil_ia = resultado["perfil"]

    if resultado["alerta_riesgo"]:
        sugerencia = resultado.get("sugerencia_rebalanceo", "")
        db.add(Alerta(usuario_id=current_user.id, tipo="warning", modulo="robo_advisor",
                      titulo="Alerta de riesgo — Robo-Advisor", mensaje=sugerencia))
        email_alerta_riesgo(current_user.email, current_user.nombre,
                            resultado["perfil"], sugerencia)

    await db.commit()
    return resultado


@router.get("/historial")
async def robo_historial(limit: int = 10,
                          current_user: Usuario = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        select(AnalisisRoboAdvisor)
        .where(AnalisisRoboAdvisor.usuario_id == current_user.id)
        .order_by(AnalisisRoboAdvisor.fecha.desc())
        .limit(limit)
    )
    return [a.to_dict() for a in res.scalars().all()]
