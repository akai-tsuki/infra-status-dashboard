"""Flaskアプリケーション本体。"""

import os

from flask import Flask, send_from_directory

from app.api import api_bp
from app.config import Config, Secrets

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")


def create_app(cfg: Config, secrets: Secrets) -> Flask:
    app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="")
    app.config["INFRA_CONFIG"] = cfg
    app.config["INFRA_SECRETS"] = secrets
    app.register_blueprint(api_bp)

    @app.route("/")
    def index():
        return send_from_directory(STATIC_DIR, "index.html")

    return app
