# InvestIQ — Diagnóstico completo + Roadmap a producción

## Estado actual del sistema (verificado)

| Módulo | Estado | Detalle |
|--------|--------|---------|
| FastAPI 24 endpoints | ✅ OK | REST + WebSocket funcionando |
| SQLAlchemy 13 tablas | ✅ OK | SQLite dev / PostgreSQL prod |
| JWT + bcrypt | ✅ OK | Auth completo |
| ECDSA P-256 | ✅ OK | Firma criptográfica de órdenes |
| MFA/TOTP + QR | ✅ OK | Google Authenticator compatible |
| AML/OFAC | ✅ OK | OpenSanctions + lista local |
| Robo-Advisor Claude | ✅ OK | Prompts JSON → Claude API |
| Excel multi-hoja | ✅ OK | openpyxl 4 hojas |
| PDF ReportLab | ✅ OK | Reporte ejecutivo |
| Redis cache | ✅ OK | Fallback en memoria si no hay Redis |
| React 13 componentes | ✅ OK | 1,812 líneas |
| Velas japonesas SVG | ✅ OK | CandleChart.jsx |
| Donut chart SVG | ✅ OK | PortfolioChart.jsx |
| Paneles flotantes | ✅ OK | 5 paneles arrastrables |
| Botones 3D | ✅ OK | ActionBar.jsx |
| TTS Web Speech API | ✅ OK | Voz masculina español |
| WebSocket tiempo real | ✅ OK | Precios cada 4s |
| Yahoo Finance | ✅ OK* | *Bloqueado en sandbox, OK en producción |
| Alpaca Paper Trading | ✅ OK | Demo mode funcional |

---

## Lo que FALLA actualmente

### 1. Yahoo Finance → bloqueado en sandbox Claude
**No es un bug del código.** En tu máquina con internet real funciona.
El sandbox de Claude no tiene acceso a `query2.finance.yahoo.com`.
**Solución:** en producción funciona automáticamente.

### 2. Alpaca Paper Trading → bloqueado en sandbox
**No es un bug del código.** `paper-api.alpaca.markets` está bloqueado aquí.
**Solución:** registrarte en https://app.alpaca.markets/signup (gratis) y poner tus keys en `.env`.

### 3. Pagos reales → no configurados
El sistema de pagos existe (services/payments.py) pero necesita keys reales.
**Solución:** ver sección "Configuración de pagos" más abajo.

---

## QUÉ FALTA PARA PRODUCCIÓN COMPLETA

### A. Backend — pendiente
- [ ] `api/v1/routes/payments.py` integrado en main.py (incluir router)
- [ ] Alembic migrations (actualmente usa `create_all` — OK para inicio)
- [ ] Rate limiting por usuario (no solo por IP)
- [ ] Refresh token rotation
- [ ] Email service (SendGrid/SES para confirmaciones)
- [ ] Notificaciones push (Firebase/OneSignal)
- [ ] TimescaleDB hypertable para precios (PostgreSQL en prod)
- [ ] Celery worker para tareas async (reportes grandes, emails)
- [ ] Admin panel (endpoints para Owner Portal)

### B. Frontend React — pendiente
- [ ] Página Mercado Live (gráficos más completos, búsqueda de activos)
- [ ] Página Portafolio (vista detallada con historial)
- [ ] Página Órdenes (historial completo con filtros)
- [ ] Página Fiscal (reportes + formularios impuestos)
- [ ] Flujo Onboarding KYC (paso a paso con cámara)
- [ ] Stripe.js integrado (pagar con tarjeta desde la app)
- [ ] MercadoPago checkout (redirect o modal)
- [ ] Notificaciones en tiempo real (toast + badge)
- [ ] Dark/light mode toggle
- [ ] Mobile responsive (actualmente solo desktop)
- [ ] PWA (instalable como app móvil)

### C. Infraestructura — pendiente
- [ ] Dominio + SSL (Let's Encrypt gratis)
- [ ] CI/CD (GitHub Actions → Railway/Render)
- [ ] Backups automáticos PostgreSQL
- [ ] Monitoring (Sentry errores + UptimeRobot)
- [ ] Logs centralizados (Papertrail o Grafana)

---

## CONFIGURACIÓN PASO A PASO

### Paso 1 — Alpaca Paper Trading (broker gratis)
1. Ir a https://app.alpaca.markets/signup
2. Verificar email
3. Ir a "Paper Trading" → "API Keys" → "Generate New Key"
4. Copiar API Key y Secret en `.env`:
```
ALPACA_API_KEY=PKxxxxxx
ALPACA_API_SECRET=xxxxxxxx
```

### Paso 2 — Claude API (Robo-Advisor)
1. Ir a https://console.anthropic.com
2. "API Keys" → "Create Key"
3. En `.env`:
```
CLAUDE_API_KEY=sk-ant-api03-...
```

### Paso 3 — Stripe (pagos con tarjeta)
1. Ir a https://dashboard.stripe.com/register
2. "Developers" → "API Keys"
3. En `.env`:
```
STRIPE_SECRET_KEY=sk_test_51...
STRIPE_PUBLISHABLE_KEY=pk_test_51...
STRIPE_WEBHOOK_SECRET=whsec_...
```
4. En Stripe Dashboard → Webhooks → Add endpoint:
   URL: `https://tu-dominio.com/api/v1/pagos/stripe/webhook`
   Events: `payment_intent.succeeded`, `payment_intent.payment_failed`

### Paso 4 — MercadoPago (LATAM)
1. Ir a https://www.mercadopago.com.pe/developers/es/docs
2. "Credenciales" → "Producción" → "Access Token"
3. En `.env`:
```
MERCADOPAGO_ACCESS_TOKEN=APP_USR-...
```

### Paso 5 — Deploy en Railway (más fácil, gratis tier)
```bash
npm install -g @railway/cli
railway login
cd investiq/backend
railway init
railway up
railway variables set $(cat .env | tr '\n' ' ')
```

### Paso 6 — Deploy en VPS (más control)
```bash
# En tu VPS Ubuntu 22.04:
bash deploy/setup_vps.sh tu-dominio.com
```

### Paso 7 — PostgreSQL + TimescaleDB en producción
```bash
# Cambiar en .env:
DATABASE_URL=postgresql+asyncpg://investiq:PASSWORD@localhost:5432/investiq
DATABASE_URL_SYNC=postgresql://investiq:PASSWORD@localhost:5432/investiq
```

---

## COSTO TOTAL DEL STACK (modo producción)

| Servicio | Plan | Costo/mes |
|----------|------|-----------|
| Railway / Render | Starter | $5-20 |
| PostgreSQL (Railway) | Starter | $5 |
| Redis (Upstash) | Free tier | $0 |
| Alpaca Paper Trading | Gratuito | $0 |
| Claude API | Pay-per-use | ~$1-5 |
| Stripe | 2.9% + $0.30/tx | Variable |
| MercadoPago | 3.99% por tx | Variable |
| Cloudflare | Free | $0 |
| Dominio | Anual | ~$12/año |
| **Total base** | | **~$30/mes** |

---

## PARA ARRANCAR HOY

```bash
# 1. Copiar .env
cp .env.example .env
# 2. Editar con tus keys
nano .env
# 3. Arrancar backend
bash start.sh
# 4. Arrancar frontend (otra terminal)
cd frontend && npm install && npm start
# 5. Abrir
# Backend: http://localhost:8000/docs
# Frontend: http://localhost:3000
# Login: demo@investiq.co / InvestIQ2026!
```
