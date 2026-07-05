#!/usr/bin/env python3
"""Servidor para Ruleta 3D - Artemis Lab"""

from flask import Flask, render_template_string
from pathlib import Path
import os

app = Flask(__name__)

# Leer el HTML de la ruleta
ROULETTE_HTML = Path("roulette3d.html").read_text(encoding="utf-8")

@app.route("/")
def index():
    return render_template_string(ROULETTE_HTML)

@app.route("/roulette3d.html")
def roulette():
    return render_template_string(ROULETTE_HTML)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
