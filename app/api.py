"""REST API（Flask Blueprint）。"""

from flask import Blueprint, current_app, jsonify

from app.checker import run_checks

api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.route("/status")
def get_status():
    cfg = current_app.config["INFRA_CONFIG"]
    secrets = current_app.config["INFRA_SECRETS"]
    result = run_checks(cfg, secrets)
    return jsonify(result)


@api_bp.route("/config")
def get_config():
    cfg = current_app.config["INFRA_CONFIG"]
    env = cfg.environments[0]
    return jsonify(
        {
            "environment": env.name,
            "polling": {
                "interval_seconds": cfg.polling.interval_seconds,
                "auto_refresh": cfg.polling.auto_refresh,
            },
        }
    )
