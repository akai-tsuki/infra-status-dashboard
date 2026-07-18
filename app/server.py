"""Flaskアプリケーション本体。"""

from flask import Flask

from app.api import api_bp
from app.config import Config, Secrets


def create_app(cfg: Config, secrets: Secrets) -> Flask:
    app = Flask(__name__)
    app.config["INFRA_CONFIG"] = cfg
    app.config["INFRA_SECRETS"] = secrets
    app.register_blueprint(api_bp)
    return app
