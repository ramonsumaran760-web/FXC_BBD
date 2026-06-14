"""
AML routes — Anti-Money Laundering checks
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.security import get_current_user
from core.rate_limit import limiter, get_limit
from models.models import Usuario, AMLLog, AuditLog, Alerta
from services.services import aml_check_entidad
from services.notification_service import notificar_aml_bloqueado
from core.monitoring import alerta_aml_blocked

router = APIRouter(prefix="/aml", tags=["aml"])


@router.post("/check")
@limiter.limit(get_limit("aml_check"))
async def aml_check(request: Request,
                    current_user: Usuario = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db)):
    body = await request.json()
    entidad = body.get("entidad", "")
    if not entidad:
        raise HTTPException(400, "Se requiere 'entidad' para verificar")

    resultado = aml_check_entidad(entidad, body.get("nit"))

    log = AMLLog(
        usuario_id=current_user.id, entidad=entidad,
        tipo_check="opensanctions",
        resultado=resultado["status"],
        score=resultado["score"],
        detalle=resultado["detalle"],
        fuente=resultado["fuente"]
    )
    db.add(log)

    if resultado["status"] == "blocked":
        current_user.aml_status = "blocked"
        current_user.aml_score = resultado["score"]
        db.add(Alerta(usuario_id=current_user.id, tipo="danger", modulo="aml",
                      titulo="Cuenta bloqueada — AML",
                      mensaje=resultado["detalle"]))
        alerta_aml_blocked(current_user.id, entidad, resultado["score"])
        notificar_aml_bloqueado(current_user.id, current_user.email,
                                 current_user.phone or "")

    elif resultado["status"] == "alert":
        current_user.aml_status = "alert"
        db.add(Alerta(usuario_id=current_user.id, tipo="warning", modulo="aml",
                      titulo="Alerta AML — revisión requerida",
                      mensaje=resultado["detalle"]))

    await db.commit()
    return resultado


@router.get("/historial")
async def aml_historial(current_user: Usuario = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    res = await db.execute(
        select(AMLLog).where(AMLLog.usuario_id == current_user.id)
        .order_by(AMLLog.fecha.desc()).limit(20))
    return [l.to_dict() for l in res.scalars().all()]
