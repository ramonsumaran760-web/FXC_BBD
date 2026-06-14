#!/bin/bash
# InvestIQ — Arranque local (sin Docker)
# Uso: bash start.sh

set -e
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║        InvestIQ — Microinversión en Bolsa           ║"
echo "║        Iniciando servidor de producción...          ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# Verificar Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 no encontrado. Instálalo primero."
    exit 1
fi

# Ir al backend
cd "$(dirname "$0")/backend"

# Instalar dependencias si no están
echo "📦 Verificando dependencias..."
pip install -r requirements.txt -q --break-system-packages 2>/dev/null || \
pip install -r requirements.txt -q

# Copiar .env si no existe
if [ ! -f ".env" ] && [ -f "../.env.example" ]; then
    cp ../.env.example .env
    echo "✓ Archivo .env creado desde .env.example"
fi

echo ""
echo "✓ Backend: FastAPI + SQLAlchemy + SQLite"
echo "✓ Broker:  Alpaca Paper Trading (demo mode)"
echo "✓ IA:      Claude API (configura CLAUDE_API_KEY en .env)"
echo "✓ Crypto:  ECDSA P-256 activado"
echo "✓ AML:     OpenSanctions + OFAC local"
echo "✓ TTS:     Web Speech API (navegador)"
echo ""
echo "🚀 Servidor en: http://localhost:8000"
echo "📖 Docs API:    http://localhost:8000/docs"
echo "🔑 Demo login:  demo@investiq.co / InvestIQ2026!"
echo ""
echo "Para el frontend React (en otra terminal):"
echo "  cd frontend && npm install && npm start"
echo ""

# Arrancar
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
