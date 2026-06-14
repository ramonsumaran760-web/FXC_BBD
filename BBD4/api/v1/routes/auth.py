"""
Auth routes — login, me, mfa, refresh, logout
get_current_user extrae el usuario del JWT; logout invalida el token en Redis.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.security import (hash_password, verify_password, create_access_token,
                            create_refresh_token, decode_token, get_current_user,
                            generar_mfa_secret, verificar_totp, generar_qr_base64,
                            generar_nonce, get_public_key_pem)
from core.config import settings
from models.models import Usuario, AuditLog, Alerta
from services.services import cache_set, cache_get
from services.notification_service import email_bienvenida

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginSchema(BaseModel):
    email: str
    password: str
    mfa_token: Optional[str] = None

class RefreshSchema(BaseModel):
    refresh_token: str

class RegisterSchema(BaseModel):
    nombre: str
    email: str
    password: str
    phone: Optional[str] = None
    edad: Optional[int] = None
    tolerancia_riesgo: Optional[str] = "moderada"


@router.post("/login")
async def login(data: LoginSchema, request: Request, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Usuario).where(Usuario.email == data.email, Usuario.activo == True))
    user = res.scalar_one_or_none()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Credenciales inválidas")

    if user.mfa_activo and user.mfa_secret:
        if not data.mfa_token or not verificar_totp(user.mfa_secret, data.mfa_token):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token MFA requerido o inválido")

    user.ultimo_login = datetime.now(timezone.utc)
    db.add(AuditLog(usuario_id=user.id, accion="LOGIN", modulo="auth",
                    detalle=f"Login: {user.email}",
                    ip=request.client.host if request.client else ""))
    await db.commit()

    token = create_access_token({"sub": str(user.id), "email": user.email, "rol": user.rol})
    refresh = create_refresh_token({"sub": str(user.id)})
    return {"access_token": token, "refresh_token": refresh,
            "token_type": "bearer", "usuario": user.to_dict()}


@router.post("/register")
async def register(data: RegisterSchema, request: Request, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Usuario).where(Usuario.email == data.email))
    if res.scalar_one_or_none():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Email ya registrado")

    user = Usuario(
        nombre=data.nombre, email=data.email,
        password_hash=hash_password(data.password),
        phone=data.phone, edad=data.edad,
        tolerancia_riesgo=data.tolerancia_riesgo or "moderada",
        rol="investor", kyc_nivel="none", aml_status="pending",
        mfa_activo=False, saldo_usd=0.0
    )
    db.add(user)
    await db.flush()
    db.add(AuditLog(usuario_id=user.id, accion="REGISTRO", modulo="auth",
                    detalle=f"Nuevo usuario: {user.email}",
                    ip=request.client.host if request.client else ""))
    db.add(Alerta(usuario_id=user.id, tipo="info", modulo="sistema",
                  titulo="Bienvenido a InvestIQ",
                  mensaje="Completa tu KYC para habilitar todas las funciones."))
    await db.commit()

    email_bienvenida(user.email, user.nombre)

    token = create_access_token({"sub": str(user.id), "email": user.email, "rol": user.rol})
    refresh = create_refresh_token({"sub": str(user.id)})
    return {"access_token": token, "refresh_token": refresh,
            "token_type": "bearer", "usuario": user.to_dict()}


@router.get("/me")
async def get_me(current_user: Usuario = Depends(get_current_user)):
    return current_user.to_dict()


@router.post("/refresh")
async def refresh_token(data: RefreshSchema, db: AsyncSession = Depends(get_db)):
    try:
        payload = decode_token(data.refresh_token)
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token inválido")

    if payload.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Tipo de token incorrecto")

    jti = payload.get("jti")
    if jti and cache_get(f"blacklist:{jti}"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token revocado")

    user_id = int(payload.get("sub", 0))
    res = await db.execute(select(Usuario).where(Usuario.id == user_id, Usuario.activo == True))
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario no encontrado")

    new_token = create_access_token({"sub": str(user.id), "email": user.email, "rol": user.rol})
    return {"access_token": new_token, "token_type": "bearer"}


@router.post("/logout")
async def logout(request: Request, current_user: Usuario = Depends(get_current_user)):
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "").replace("bearer ", "")
    try:
        payload = decode_token(token)
        jti = payload.get("jti")
        exp = payload.get("exp", 0)
        ttl = max(0, exp - int(datetime.now(timezone.utc).timestamp()))
        if jti:
            cache_set(f"blacklist:{jti}", "1", ttl=max(ttl, 60))
    except Exception:
        pass
    return {"ok": True, "mensaje": "Sesión cerrada"}


@router.get("/mfa/setup")
async def mfa_setup(current_user: Usuario = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db)):
    secret = generar_mfa_secret()
    qr = generar_qr_base64(secret, current_user.email)
    current_user.mfa_secret = secret
    await db.commit()
    return {"secret": secret, "qr_base64": qr,
            "instrucciones": "Escanea con Google Authenticator"}


@router.post("/mfa/enable")
async def mfa_enable(token_otp: str, current_user: Usuario = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)):
    if not current_user.mfa_secret:
        raise HTTPException(400, "Primero llama /mfa/setup")
    if not verificar_totp(current_user.mfa_secret, token_otp):
        raise HTTPException(400, "Token OTP inválido")
    current_user.mfa_activo = True
    await db.commit()
    return {"ok": True, "mfa_activo": True}


@router.get("/pubkey")
async def get_pubkey():
    return {"public_key_pem": get_public_key_pem(),
            "algoritmo": "ECDSA P-256 / SHA-256",
            "uso": "Verificación de firmas de órdenes"}
