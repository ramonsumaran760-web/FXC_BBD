"""
Market routes — precios, velas, activos
"""
from typing import Optional
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.rate_limit import limiter, get_limit
from models.models import Activo
from services.services import get_market_prices, get_candles, cache_get, cache_set
from datetime import datetime

router = APIRouter(prefix="/mercado", tags=["mercado"])


@router.get("/precios")
@limiter.limit(get_limit("mercado_precios"))
async def precios(request: Request, tickers: Optional[str] = None):
    t = tickers.split(",") if tickers else None
    cached = cache_get("precios_mercado")
    if cached:
        return cached
    data = get_market_prices(t)
    cache_set("precios_mercado", data, ttl=15)
    return data


@router.get("/candles/{ticker}")
@limiter.limit(get_limit("mercado_candles"))
async def candles(request: Request, ticker: str,
                  period: str = "1mo", interval: str = "1d"):
    key = f"candles_{ticker}_{period}_{interval}"
    cached = cache_get(key)
    if cached:
        return {"ticker": ticker, "candles": cached}
    data = get_candles(ticker.upper(), period, interval)
    cache_set(key, data, ttl=60)
    return {"ticker": ticker, "period": period, "interval": interval, "candles": data}


@router.get("/activos")
async def get_activos(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Activo).where(Activo.activo == True))
    activos = res.scalars().all()
    prices = get_market_prices([a.ticker for a in activos])
    for a in activos:
        p = prices.get(a.ticker, {})
        a.precio_actual = p.get("price", a.precio_actual)
        a.variacion_pct = p.get("change_pct", 0)
        a.ultima_actualizacion = datetime.utcnow()
    await db.commit()
    return [a.to_dict() for a in activos]
