"""
workers/backup_worker.py — Backups automáticos PostgreSQL + SQLite
Estrategia: diario local + semanal S3 + retención 30 días
"""
import os, subprocess, logging, gzip, shutil
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────
BACKUP_DIR = os.getenv("BACKUP_DIR", "./backups")
DB_URL_SYNC = os.getenv("DATABASE_URL_SYNC", "sqlite:///./investiq.db")
S3_BUCKET = os.getenv("BACKUP_S3_BUCKET", "")
S3_PREFIX = os.getenv("BACKUP_S3_PREFIX", "investiq/backups/")
RETAIN_DAYS = int(os.getenv("BACKUP_RETAIN_DAYS", "30"))
NOTIFY_EMAIL = os.getenv("BACKUP_NOTIFY_EMAIL", "")

os.makedirs(BACKUP_DIR, exist_ok=True)


def timestamp() -> str:
    return datetime.utcnow().strftime("%Y%m%d_%H%M%S")


# ── SQLite backup (dev) ───────────────────────────────────────────────────
def backup_sqlite() -> str | None:
    """Copia el archivo SQLite y lo comprime."""
    db_path = DB_URL_SYNC.replace("sqlite:///", "").replace("sqlite://", "")
    if not os.path.exists(db_path):
        logger.warning(f"SQLite no encontrado en {db_path}")
        return None
    nombre = f"investiq_sqlite_{timestamp()}.db.gz"
    destino = os.path.join(BACKUP_DIR, nombre)
    try:
        with open(db_path, "rb") as f_in, gzip.open(destino, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        size = os.path.getsize(destino)
        logger.info(f"Backup SQLite: {nombre} ({size:,} bytes)")
        return destino
    except Exception as e:
        logger.error(f"Error backup SQLite: {e}")
        return None


# ── PostgreSQL backup (producción) ────────────────────────────────────────
def backup_postgres() -> str | None:
    """
    Ejecuta pg_dump y comprime el resultado.
    Requiere: apt install postgresql-client
    """
    # Parsear DATABASE_URL
    url = DB_URL_SYNC
    if "postgresql" not in url:
        return backup_sqlite()

    try:
        # Extraer componentes de la URL
        # postgresql://user:pass@host:port/dbname
        url_clean = url.replace("postgresql://", "").replace("postgresql+asyncpg://", "")
        user_pass, host_db = url_clean.split("@")
        user, password = user_pass.split(":")
        host_port, dbname = host_db.split("/")
        host, port = (host_port.split(":") + ["5432"])[:2]

        nombre = f"investiq_pg_{timestamp()}.sql.gz"
        destino = os.path.join(BACKUP_DIR, nombre)

        env = os.environ.copy()
        env["PGPASSWORD"] = password

        cmd = [
            "pg_dump",
            f"--host={host}",
            f"--port={port}",
            f"--username={user}",
            f"--dbname={dbname}",
            "--no-password",
            "--format=plain",
            "--clean",
            "--if-exists",
            "--create",
        ]

        with gzip.open(destino, "wb") as f_out:
            result = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env=env, timeout=120
            )
            if result.returncode != 0:
                raise Exception(result.stderr.decode())
            f_out.write(result.stdout)

        size = os.path.getsize(destino)
        logger.info(f"Backup PostgreSQL: {nombre} ({size:,} bytes)")
        return destino

    except Exception as e:
        logger.error(f"Error backup PostgreSQL: {e}")
        return None


# ── Upload a S3 ───────────────────────────────────────────────────────────
def upload_s3(archivo: str) -> bool:
    """Sube el backup a AWS S3. Requiere boto3 + credenciales AWS."""
    if not S3_BUCKET:
        logger.info("S3_BUCKET no configurado — backup solo local")
        return False
    try:
        import boto3
        s3 = boto3.client("s3")
        nombre = os.path.basename(archivo)
        key = f"{S3_PREFIX}{nombre}"
        s3.upload_file(archivo, S3_BUCKET, key,
                       ExtraArgs={"StorageClass": "STANDARD_IA"})
        logger.info(f"Backup subido a S3: s3://{S3_BUCKET}/{key}")
        return True
    except ImportError:
        logger.warning("boto3 no instalado: pip install boto3")
        return False
    except Exception as e:
        logger.error(f"Error upload S3: {e}")
        return False


# ── Rotación (eliminar backups viejos) ────────────────────────────────────
def rotar_backups_locales(dias: int = RETAIN_DAYS) -> int:
    """Elimina backups locales más viejos que `dias` días."""
    limite = datetime.utcnow() - timedelta(days=dias)
    eliminados = 0
    for f in Path(BACKUP_DIR).glob("investiq_*.gz"):
        if datetime.utcfromtimestamp(f.stat().st_mtime) < limite:
            f.unlink()
            eliminados += 1
            logger.info(f"Backup expirado eliminado: {f.name}")
    return eliminados


def rotar_s3(dias: int = RETAIN_DAYS) -> int:
    """Elimina backups en S3 más viejos que `dias` días."""
    if not S3_BUCKET:
        return 0
    try:
        import boto3
        s3 = boto3.client("s3")
        limite = datetime.utcnow() - timedelta(days=dias)
        paginator = s3.get_paginator("list_objects_v2")
        eliminados = 0
        for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=S3_PREFIX):
            for obj in page.get("Contents", []):
                if obj["LastModified"].replace(tzinfo=None) < limite:
                    s3.delete_object(Bucket=S3_BUCKET, Key=obj["Key"])
                    eliminados += 1
        logger.info(f"S3 rotación: {eliminados} backups eliminados")
        return eliminados
    except Exception as e:
        logger.error(f"Error rotación S3: {e}")
        return 0


# ── Notificación por email ────────────────────────────────────────────────
def notificar_backup(archivo: str, s3_ok: bool, error: str = None):
    if not NOTIFY_EMAIL:
        return
    try:
        from services.email_service import _send
        estado = "✓ Exitoso" if not error else f"✗ Error: {error}"
        size = os.path.getsize(archivo) if archivo and os.path.exists(archivo) else 0
        _send(NOTIFY_EMAIL, f"InvestIQ Backup — {estado}", f"""
<h3>Reporte de Backup — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</h3>
<p>Estado: <b>{estado}</b></p>
<p>Archivo: {os.path.basename(archivo) if archivo else 'N/A'}</p>
<p>Tamaño: {size:,} bytes</p>
<p>S3: {'✓ Subido' if s3_ok else '✗ No subido'}</p>
""")
    except Exception:
        pass


# ── Función principal ─────────────────────────────────────────────────────
def ejecutar_backup(tipo: str = "diario") -> dict:
    """
    Ejecuta el ciclo completo de backup:
    1. pg_dump (o sqlite)
    2. Upload S3
    3. Rotación local
    4. Rotación S3
    5. Notificación
    """
    logger.info(f"Iniciando backup {tipo} — {datetime.utcnow().isoformat()}")
    archivo = None
    s3_ok = False
    error = None

    try:
        archivo = backup_postgres()
        if not archivo:
            raise Exception("No se generó archivo de backup")
        s3_ok = upload_s3(archivo)
        eliminados_local = rotar_backups_locales()
        eliminados_s3 = rotar_s3() if tipo == "semanal" else 0
        resultado = {
            "ok": True,
            "archivo": archivo,
            "s3": s3_ok,
            "eliminados_local": eliminados_local,
            "eliminados_s3": eliminados_s3,
            "timestamp": datetime.utcnow().isoformat()
        }
        logger.info(f"Backup completado: {resultado}")
    except Exception as e:
        error = str(e)
        logger.error(f"Backup FALLIDO: {error}")
        resultado = {"ok": False, "error": error, "timestamp": datetime.utcnow().isoformat()}

    notificar_backup(archivo or "", s3_ok, error)
    return resultado


# ── Celery tasks (registradas automáticamente si Celery está activo) ──────
try:
    from workers.celery_worker import app as celery_app

    @celery_app.task(name="workers.backup_worker.backup_diario")
    def backup_diario():
        return ejecutar_backup("diario")

    @celery_app.task(name="workers.backup_worker.backup_semanal")
    def backup_semanal():
        return ejecutar_backup("semanal")

    # Registrar en beat schedule
    celery_app.conf.beat_schedule.update({
        "backup-diario": {
            "task": "workers.backup_worker.backup_diario",
            "schedule": 86400.0,   # cada 24h
        },
        "backup-semanal": {
            "task": "workers.backup_worker.backup_semanal",
            "schedule": 604800.0,  # cada 7 días
        },
    })

except Exception:
    # Celery no disponible — las funciones igual se pueden llamar manualmente
    pass


if __name__ == "__main__":
    # Ejecutar backup manualmente: python workers/backup_worker.py
    import sys
    tipo = sys.argv[1] if len(sys.argv) > 1 else "diario"
    resultado = ejecutar_backup(tipo)
    print(f"\nResultado: {resultado}")
