"""
Security — JWT + ECDSA P-256 + bcrypt + TOTP MFA + cifrado PII + blacklist de tokens
"""
from datetime import datetime, timedelta
from typing import Optional
import json, hashlib, secrets, base64

from jose import JWTError, jwt
from passlib.context import CryptContext
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidSignature
from cryptography.fernet import Fernet, InvalidToken
import pyotp, qrcode, io

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from core.config import settings

# ── Password hashing ──────────────────────────────────────
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_ctx.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_ctx.verify(plain, hashed)

# ── JWT ──────────────────────────────────────────────────
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    jti = secrets.token_hex(16)
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "access", "jti": jti})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    jti = secrets.token_hex(16)
    expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh", "jti": jti})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError as e:
        raise ValueError(f"Token inválido: {e}")

# ── HTTP Bearer dep ───────────────────────────────────────
_bearer = HTTPBearer(auto_error=True)

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
):
    """
    Dependencia FastAPI: extrae usuario del JWT.
    Valida firma, expiración y lista negra Redis.
    Importación circular evitada: db y Usuario se importan aquí.
    """
    from sqlalchemy import select
    from core.database import AsyncSessionLocal
    from models.models import Usuario
    from services.services import cache_get

    token = credentials.credentials
    try:
        payload = decode_token(token)
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido o expirado")

    if payload.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Tipo de token incorrecto")

    jti = payload.get("jti")
    if jti and cache_get(f"blacklist:{jti}"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesión revocada")

    user_id = int(payload.get("sub", 0))
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(Usuario).where(Usuario.id == user_id, Usuario.activo == True))
        user = res.scalar_one_or_none()

    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario no encontrado o inactivo")
    return user


async def require_admin(current_user=Depends(get_current_user)):
    if current_user.rol != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Acceso restringido a administradores")
    return current_user

# ── ECDSA P-256 — Firma de órdenes ───────────────────────
_private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
_public_key = _private_key.public_key()

def firmar_orden(datos: dict) -> str:
    mensaje = json.dumps(datos, sort_keys=True, default=str).encode("utf-8")
    firma = _private_key.sign(mensaje, ec.ECDSA(hashes.SHA256()))
    return firma.hex()

def verificar_firma(datos: dict, firma_hex: str) -> bool:
    try:
        mensaje = json.dumps(datos, sort_keys=True, default=str).encode("utf-8")
        firma = bytes.fromhex(firma_hex)
        _public_key.verify(firma, mensaje, ec.ECDSA(hashes.SHA256()))
        return True
    except (InvalidSignature, ValueError, Exception):
        return False

def get_public_key_pem() -> str:
    return _public_key.public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()

# ── PII Encryption (Fernet AES-128-CBC) ──────────────────
def _get_fernet() -> Optional[Fernet]:
    key = settings.PII_ENCRYPTION_KEY
    if not key:
        return None
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception:
        return None

def encrypt_pii(value: str) -> str:
    """Cifra datos sensibles (num_doc, selfie_hash). Returns base64 string."""
    f = _get_fernet()
    if not f or not value:
        return value
    return f.encrypt(value.encode()).decode()

def decrypt_pii(value: str) -> str:
    """Descifra datos PII. Fallback: devuelve el valor tal cual."""
    f = _get_fernet()
    if not f or not value:
        return value
    try:
        return f.decrypt(value.encode()).decode()
    except (InvalidToken, Exception):
        return value

# ── MFA / TOTP ────────────────────────────────────────────
def generar_mfa_secret() -> str:
    return pyotp.random_base32()

def verificar_totp(secret: str, token: str) -> bool:
    return pyotp.TOTP(secret).verify(token, valid_window=1)

def generar_qr_base64(secret: str, email: str) -> str:
    uri = pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=settings.MFA_ISSUER)
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()

# ── Utilidades ────────────────────────────────────────────
def generar_nonce() -> str:
    return secrets.token_hex(16)

def hash_sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()
