#!/usr/bin/env python3
"""Servidor para Ruleta 3D - Artemis Lab"""

from flask import Flask, send_file, send_from_directory
from pathlib import Path
import os

app = Flask(__name__, static_folder=".", static_url_path="")

@app.route("/")
def index():
    """Servir el HTML principal"""
    return send_file("roulette3d.html", mimetype="text/html")

@app.route("/roulette3d.html")
def roulette():
    """Ruta alternativa para la ruleta"""
    return send_file("roulette3d.html", mimetype="text/html")

@app.route("/<path:filename>")
def serve_file(filename):
    """Servir archivos estáticos"""
    return send_from_directory(".", filename)

@app.errorhandler(404)
def not_found(error):
    """Redirigir 404 al index"""
    return send_file("roulette3d.html", mimetype="text/html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
