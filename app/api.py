"""REST API（Flask Blueprint）。

チェックの実行はStatusPollerのバックグラウンドスレッドが担い（Issue #17）、
各エンドポイントはキャッシュの参照とポーラーへの指示だけを行う。
どのエンドポイントも即時に応答する。
"""

from flask import Blueprint, current_app, jsonify, request

api_bp = Blueprint("api", __name__, url_prefix="/api")


def _poller():
    return current_app.config["INFRA_POLLER"]


@api_bp.route("/status")
def get_status():
    """キャッシュ済みのチェック結果と実行状態を返す（チェック自体は実行しない）。

    resultは初回チェック完了前はnull。checked_atはサーバ側でチェックを
    実行した時刻（キャッシュの鮮度を画面に表示するためのもの）。
    """
    return jsonify(_poller().snapshot())


@api_bp.route("/refresh", methods=["POST"])
def trigger_refresh():
    """チェックの即時実行をバックグラウンドスレッドに指示する（多重起動はしない）。"""
    poller = _poller()
    poller.trigger_refresh()
    return jsonify(poller.snapshot())


@api_bp.route("/config")
def get_config():
    cfg = current_app.config["INFRA_CONFIG"]
    snapshot = _poller().snapshot()
    return jsonify(
        {
            "environments": [env.name for env in cfg.environments],
            "current_environment": snapshot["current_environment"],
            "polling": snapshot["polling"],
        }
    )


@api_bp.route("/environment", methods=["POST"])
def set_environment():
    cfg = current_app.config["INFRA_CONFIG"]

    body = request.get_json(silent=True) or {}
    name = body.get("name")

    known_names = [env.name for env in cfg.environments]
    if name not in known_names:
        return jsonify({"error": f"unknown environment: {name!r}"}), 400

    # キャッシュは破棄され、新環境でのチェックがバックグラウンドで開始される。
    # SSH接続はチェック実行のたびに張って閉じる方式のため、切り替え時に
    # 明示的に切断すべき常駐接続は存在しない。
    poller = _poller()
    poller.set_environment(name)
    return jsonify(poller.snapshot())


@api_bp.route("/polling", methods=["POST"])
def set_polling():
    """更新間隔・自動更新ON/OFFを変更する（どちらか一方のみの指定も可）。"""
    body = request.get_json(silent=True) or {}
    interval_seconds = body.get("interval_seconds")
    auto_refresh = body.get("auto_refresh")

    if interval_seconds is not None:
        if not isinstance(interval_seconds, int) or interval_seconds < 5:
            return jsonify({"error": "interval_secondsは5以上の整数を指定してください"}), 400
    if auto_refresh is not None and not isinstance(auto_refresh, bool):
        return jsonify({"error": "auto_refreshは真偽値を指定してください"}), 400

    poller = _poller()
    poller.update_polling(interval_seconds=interval_seconds, auto_refresh=auto_refresh)
    return jsonify(poller.snapshot())
