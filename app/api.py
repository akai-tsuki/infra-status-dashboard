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
