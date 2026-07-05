#!/usr/bin/env python3
"""Servidor para Ruleta 3D - Artemis Lab"""

from flask import Flask, send_file, send_from_directory
import os
import requests
from pathlib import Path
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Obtener el directorio del script
BASE_DIR = Path(__file__).parent.absolute()
STATIC_DIR = BASE_DIR / "static"

# Crear directorio estático si no existe
STATIC_DIR.mkdir(exist_ok=True)

app = Flask(__name__, static_folder=str(BASE_DIR), static_url_path="/static")

def ensure_three_js():
    """Descargar Three.js si no existe localmente"""
    three_path = STATIC_DIR / "three.min.js"
    controls_path = STATIC_DIR / "OrbitControls.js"
    
    if not three_path.exists():
        print("Downloading Three.js r128...")
        try:
            url = "https://cdn.jsdelivr.net/npm/three@r128/build/three.min.js"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                three_path.write_text(resp.text)
                print(f"✓ Three.js saved to {three_path}")
        except Exception as e:
            print(f"⚠ Could not download Three.js: {e}")
    
    if not controls_path.exists():
        print("Downloading OrbitControls...")
        try:
            url = "https://cdn.jsdelivr.net/npm/three@r128/examples/js/controls/OrbitControls.js"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                controls_path.write_text(resp.text)
                print(f"✓ OrbitControls saved to {controls_path}")
        except Exception as e:
            print(f"⚠ Could not download OrbitControls: {e}")

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

@app.route("/static/<path:filename>")
def serve_static(filename):
    """Servir archivos estáticos (Three.js, etc)"""
    return send_from_directory(STATIC_DIR, filename)

@app.errorhandler(404)
def not_found(error):
    """Redirigir 404 al index"""
    html_path = BASE_DIR / "roulette3d.html"
    if html_path.exists():
        return send_file(str(html_path), mimetype="text/html")
    return "Not Found", 404

if __name__ == "__main__":
    ensure_three_js()
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV") != "production"
    print(f"Starting server from {BASE_DIR}")
    print(f"Debug mode: {debug}")
    app.run(host="0.0.0.0", port=port, debug=debug, threaded=True)
