"""
Security — JWT + ECDSA P-256 + bcrypt + TOTP MFA
Cada orden de bolsa lleva firma criptográfica verificable.
"""
from datetime import datetime, timedelta
from typing import Optional
import json, hashlib, secrets

from jose import JWTError, jwt
from passlib.context import CryptContext
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidSignature
import pyotp, qrcode, io, base64

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
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError as e:
        raise ValueError(f"Token inválido: {e}")

# ── ECDSA P-256 — Firma de órdenes ───────────────────────
# En producción: cargar desde HSM o secrets manager
_private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
_public_key = _private_key.public_key()

def firmar_orden(datos: dict) -> str:
    """Firma criptográfica ECDSA P-256 de una orden. Retorna hex."""
    mensaje = json.dumps(datos, sort_keys=True, default=str).encode("utf-8")
    firma = _private_key.sign(mensaje, ec.ECDSA(hashes.SHA256()))
    return firma.hex()

def verificar_firma(datos: dict, firma_hex: str) -> bool:
    """Verifica firma ECDSA de una orden."""
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

# ── MFA / TOTP ────────────────────────────────────────────
def generar_mfa_secret() -> str:
    return pyotp.random_base32()

def verificar_totp(secret: str, token: str) -> bool:
    totp = pyotp.TOTP(secret)
    return totp.verify(token, valid_window=1)

def generar_qr_base64(secret: str, email: str) -> str:
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=email, issuer_name=settings.MFA_ISSUER)
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()

# ── Utilidades ────────────────────────────────────────────
def generar_nonce() -> str:
    return secrets.token_hex(16)

def hash_sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()
