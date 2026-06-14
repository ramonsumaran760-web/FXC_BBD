"""
KYC routes — verificación de identidad con cifrado PII
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.security import get_current_user, encrypt_pii, hash_sha256
from core.rate_limit import limiter, get_limit
from models.models import Usuario, KYCVerificacion, AuditLog, Alerta
from services.notification_service import email_kyc_aprobado

router = APIRouter(prefix="/kyc", tags=["kyc"])


@router.post("/submit")
@limiter.limit(get_limit("kyc_submit"))
async def kyc_submit(request: Request,
                     current_user: Usuario = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)):
    body = await request.json()

    num_doc = body.get("num_doc", "")
    # Cifrar el número de documento en reposo
    num_doc_cifrado = encrypt_pii(num_doc) if num_doc else ""
    doc_hash = hash_sha256(num_doc) if num_doc else ""

    kyc = KYCVerificacion(
        usuario_id=current_user.id,
        tipo_doc=body.get("tipo_doc", "cedula"),
        num_doc_cifrado=num_doc_cifrado,
        doc_hash=doc_hash,
        pais_emision=body.get("pais", "CO"),
        nivel_alcanzado="basic",
        proveedor="local",
        resultado="approved"
    )
    db.add(kyc)

    current_user.kyc_nivel = "basic"
    current_user.kyc_verificado = True
    current_user.kyc_fecha = datetime.now(timezone.utc)

    db.add(AuditLog(usuario_id=current_user.id, accion="KYC_SUBMIT",
                    modulo="kyc", detalle="KYC básico completado",
                    ip=request.client.host if request.client else ""))
    db.add(Alerta(usuario_id=current_user.id, tipo="success", modulo="kyc",
                  titulo="KYC aprobado",
                  mensaje="Tu identidad fue verificada al nivel básico."))
    await db.commit()

    email_kyc_aprobado(current_user.email, current_user.nombre, "basic")

    return {"ok": True, "nivel": "basic", "mensaje": "KYC básico aprobado"}


@router.get("/status")
async def kyc_status(current_user: Usuario = Depends(get_current_user)):
    return {
        "kyc_nivel": current_user.kyc_nivel,
        "kyc_verificado": current_user.kyc_verificado,
        "kyc_fecha": current_user.kyc_fecha.isoformat() if current_user.kyc_fecha else None,
        "proximos_pasos": _proximos_pasos(current_user.kyc_nivel)
    }


def _proximos_pasos(nivel: str) -> list:
    mapa = {
        "none": ["Enviar cédula o pasaporte", "Completar formulario KYC básico"],
        "basic": ["Selfie en vivo para verificación biométrica", "Comprobante de ingresos"],
        "full": ["Verificación biométrica avanzada (nivel máximo)"],
        "biometric": [],
    }
    return mapa.get(nivel, [])
