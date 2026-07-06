#!/usr/bin/env python3
"""Servidor para Ruleta 3D - Artemis Lab"""

from flask import Flask, send_file, send_from_directory, request
import os
from pathlib import Path
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Obtener el directorio del script
BASE_DIR = Path(__file__).parent.absolute()

app = Flask(__name__, static_folder=str(BASE_DIR), static_url_path="/static")

ASSET_SUFFIXES = (
    ".js", ".mjs", ".css", ".map", ".json",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
    ".ico", ".woff", ".woff2", ".ttf", ".otf"
)

@app.route("/")
def index():
    """Servir la ruleta con física en tiempo real"""
    html_path = BASE_DIR / "roulette_physics.html"
    if not html_path.exists():
        return f"Error: roulette_physics.html not found at {html_path}", 500
    return send_file(str(html_path), mimetype="text/html")

@app.route("/roulette3d.html")
def roulette_3d():
    """Ruleta 3D original"""
    html_path = BASE_DIR / "roulette3d.html"
    return send_file(str(html_path), mimetype="text/html")

@app.route("/roulette_physics.html")
def roulette_physics():
    """Ruleta con motor de física"""
    html_path = BASE_DIR / "roulette_physics.html"
    return send_file(str(html_path), mimetype="text/html")

@app.route("/vendor/<path:filename>")
def vendor_files(filename):
    """Servir modulos locales de three.js y dependencias."""
    vendor_dir = BASE_DIR / "vendor"
    return send_from_directory(str(vendor_dir), filename)

@app.errorhandler(404)
def not_found(error):
    """Evitar fallback HTML para assets; fallback solo para rutas de pagina."""
    path = request.path.lower()
    if path.endswith(ASSET_SUFFIXES) or path.startswith("/vendor/"):
        return "Not Found", 404
    html_path = BASE_DIR / "roulette3d.html"
    if html_path.exists():
        return send_file(str(html_path), mimetype="text/html")
    return "Not Found", 404

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV") != "production"
    print(f"Starting server from {BASE_DIR}")
    print(f"Debug mode: {debug}")
    app.run(host="0.0.0.0", port=port, debug=debug, threaded=True)
