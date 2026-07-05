#!/usr/bin/env python3
"""Servidor para Ruleta 3D - Artemis Lab"""

from flask import Flask, send_file
import os
from pathlib import Path

# Obtener el directorio del script
BASE_DIR = Path(__file__).parent.absolute()

app = Flask(__name__, static_folder=str(BASE_DIR), static_url_path="/static")

@app.route("/")
def index():
    """Servir la ruleta 3D realista por defecto"""
    html_path = BASE_DIR / "roulette3d.html"
    if not html_path.exists():
        return f"Error: roulette3d.html not found at {html_path}", 500
    return send_file(str(html_path), mimetype="text/html")

@app.route("/roulette_real.html")
def roulette_real():
    """Ruleta con canvas (más realista)"""
    html_path = BASE_DIR / "roulette_real.html"
    return send_file(str(html_path), mimetype="text/html")

@app.route("/roulette3d.html")
def roulette_3d():
    """Ruleta 3D original"""
    html_path = BASE_DIR / "roulette3d.html"
    return send_file(str(html_path), mimetype="text/html")

@app.errorhandler(404)
def not_found(error):
    """Redirigir 404 al index"""
    html_path = BASE_DIR / "roulette3d.html"
    if html_path.exists():
        return send_file(str(html_path), mimetype="text/html")
    return "Not Found", 404

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Starting server from {BASE_DIR}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
