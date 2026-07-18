"""Flaskアプリケーション本体。"""

import os

from flask import Flask, send_from_directory

from app.api import api_bp
from app.config import Config, Secrets
from app.poller import StatusPoller

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")


def create_app(cfg: Config, secrets: Secrets) -> Flask:
    app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="")
    app.config["INFRA_CONFIG"] = cfg
    app.config["INFRA_SECRETS"] = secrets

    # チェックはバックグラウンドスレッドが定期実行し、APIはキャッシュを返す
    # （Issue #17）。デーモンスレッドのため、プロセス終了時は一緒に終了する。
    poller = StatusPoller(cfg, secrets, env_name=cfg.environments[0].name)
    app.config["INFRA_POLLER"] = poller
    poller.start()

    app.register_blueprint(api_bp)

    @app.route("/")
    def index():
        return send_from_directory(STATIC_DIR, "index.html")

    return app
