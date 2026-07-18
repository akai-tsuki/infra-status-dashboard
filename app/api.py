"""REST API（Flask Blueprint）。"""

from flask import Blueprint, current_app, jsonify, request

from app.checker import run_checks

api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.route("/status")
def get_status():
    cfg = current_app.config["INFRA_CONFIG"]
    secrets = current_app.config["INFRA_SECRETS"]
    state = current_app.config["INFRA_STATE"]
    result = run_checks(cfg, secrets, env_name=state.current_env_name)
    return jsonify(result)


@api_bp.route("/config")
def get_config():
    cfg = current_app.config["INFRA_CONFIG"]
    state = current_app.config["INFRA_STATE"]
    return jsonify(
        {
            "environments": [env.name for env in cfg.environments],
            "current_environment": state.current_env_name,
            "polling": {
                "interval_seconds": cfg.polling.interval_seconds,
                "auto_refresh": cfg.polling.auto_refresh,
            },
        }
    )


@api_bp.route("/environment", methods=["POST"])
def set_environment():
    cfg = current_app.config["INFRA_CONFIG"]
    state = current_app.config["INFRA_STATE"]

    body = request.get_json(silent=True) or {}
    name = body.get("name")

    known_names = [env.name for env in cfg.environments]
    if name not in known_names:
        return jsonify({"error": f"unknown environment: {name!r}"}), 400

    # 現在は接続をリクエストごとに都度張って都度閉じる方式のため、切り替え時に
    # 明示的に切断すべき常駐接続は存在しない。次回以降のチェック実行から
    # 新しい環境の踏み台に接続される。
    state.set_current_env_name(name)
    return jsonify({"current_environment": name})
