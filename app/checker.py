"""チェック実行モジュール。

設定内の1つの環境に対して踏み台経由で多段SSH接続し、各対象サーバに
割り当てられたロールのチェックをまとめて実行する。

接続失敗・認証情報不足・コマンド実行失敗（タイムアウト含む）は、その場で
例外を伝播させず、該当箇所（踏み台全体／対象サーバ単位／チェック単位）の
エラーとして結果に含める。1台の対象サーバやコマンドが失敗しても、
他の対象サーバ・チェックの結果は影響を受けずに返せるようにするため。

さらに、接続関連の失敗は「ネットワーク到達」「SSH認証」「多段接続」の
どの段階で起きたのかを区別して結果に含める（stages）。SSH接続自体は
成功しているのにチェックコマンドが失敗しているだけの状態と、そもそも
踏み台や対象サーバに繋がっていない状態を、画面上で見分けられるようにする
ため。事前処理・ログイン（oc login等）の段階は未実装で、実装時にここへ
追加する想定。
"""

from __future__ import annotations

import socket

import paramiko

from app.config import Config, Secrets, Target
from app.sshclient import SSHConnection

# コマンド実行時に起こりうる想定内のエラー（認証失敗・タイムアウト・
# 接続拒否・DNS解決失敗等）。これ以外の例外（プログラムのバグ等）は
# 意図的に捕捉せず、そのままFlaskの500エラーとして扱う。
CONNECTION_ERRORS = (paramiko.SSHException, OSError)

# ネットワーク到達レベルのエラー（DNS解決・接続拒否・タイムアウト）。
# socket.gaierror/ConnectionRefusedError/TimeoutErrorはいずれもOSErrorの
# サブクラスなので、より具体的なメッセージにするために先に判定する。
_NETWORK_ERRORS = (socket.gaierror, ConnectionRefusedError, TimeoutError, OSError)


def _classify_connection_error(e: Exception) -> str:
    """接続エラーの種類を判定し、分かりやすい日本語メッセージにする。"""
    if isinstance(e, socket.gaierror):
        return f"ホスト名の解決に失敗しました（DNS）: {e}"
    if isinstance(e, (ConnectionRefusedError, TimeoutError)):
        return f"接続に失敗しました（接続拒否またはタイムアウト）: {e}"
    if isinstance(e, paramiko.ChannelException):
        # 多段接続で、踏み台から対象サーバへのTCP到達に失敗した場合
        return f"対象サーバへの到達に失敗しました（DNS解決失敗・接続拒否等）: {e}"
    if isinstance(e, paramiko.AuthenticationException):
        return f"認証に失敗しました: {e}"
    if isinstance(e, paramiko.SSHException):
        return f"SSH接続に失敗しました: {e}"
    return f"接続に失敗しました: {e}"


def _stage(ok: bool, message: str | None = None) -> dict:
    return {"ok": ok, "message": message}


def _check_names_for_target(cfg: Config, target: Target) -> list[str]:
    """対象サーバのrolesから実行すべきチェック名を重複除去した上で返す。"""
    names: list[str] = []
    for role in target.roles:
        for check_name in cfg.roles.get(role, []):
            if check_name not in names:
                names.append(check_name)
    return names


def _run_target_checks(cfg: Config, target: Target, target_conn: SSHConnection) -> list[dict]:
    checks = []
    for check_name in _check_names_for_target(cfg, target):
        check_def = cfg.check_definitions[check_name]
        try:
            stdout, stderr, exit_status = target_conn.run_command(check_def.command)
            checks.append(
                {
                    "name": check_name,
                    "command": check_def.command,
                    "parser": check_def.parser,
                    "exit_status": exit_status,
                    "stdout": stdout,
                    "stderr": stderr,
                    "error": None,
                }
            )
        except CONNECTION_ERRORS as e:
            checks.append(
                {
                    "name": check_name,
                    "command": check_def.command,
                    "parser": check_def.parser,
                    "exit_status": None,
                    "stdout": "",
                    "stderr": "",
                    "error": f"コマンド実行に失敗しました: {e}",
                }
            )
    return checks


def _run_target(cfg: Config, secrets_for_env, bastion: SSHConnection, target: Target) -> dict:
    target_secret = secrets_for_env.targets.get(target.name)
    if target_secret is None:
        return {
            "name": target.name,
            "host": target.host,
            "roles": target.roles,
            "stages": {
                "target_connect": _stage(
                    False, f"secrets.yamlに対象サーバ「{target.name}」の認証情報がありません"
                )
            },
            "checks": [],
        }

    try:
        channel = bastion.open_channel_to(target.host, target.port)
        target_conn = SSHConnection(
            host=target.host,
            port=target.port,
            username=target_secret.username,
            key_filename=target_secret.private_key_path,
            sock=channel,
        )
    except CONNECTION_ERRORS as e:
        return {
            "name": target.name,
            "host": target.host,
            "roles": target.roles,
            "stages": {"target_connect": _stage(False, _classify_connection_error(e))},
            "checks": [],
        }

    with target_conn:
        checks = _run_target_checks(cfg, target, target_conn)

    return {
        "name": target.name,
        "host": target.host,
        "roles": target.roles,
        "stages": {"target_connect": _stage(True)},
        "checks": checks,
    }


def run_checks(cfg: Config, secrets: Secrets, env_name: str | None = None) -> dict:
    """指定環境（省略時はconfig.yaml先頭の環境）のチェックを実行し、結果を返す。"""
    env = cfg.environments[0]
    if env_name is not None:
        env = next(e for e in cfg.environments if e.name == env_name)

    env_secrets = secrets.environments.get(env.name)
    if env_secrets is None:
        message = f"secrets.yamlに環境「{env.name}」の認証情報がありません"
        return {
            "environment": env.name,
            "stages": {
                "bastion_network": _stage(False, message),
                "bastion_auth": _stage(False, "未実施"),
            },
            "targets": [],
        }

    try:
        bastion = SSHConnection(
            host=env.bastion.host,
            port=env.bastion.port,
            username=env_secrets.bastion.username,
            password=env_secrets.bastion.password,
        )
    except _NETWORK_ERRORS as e:
        return {
            "environment": env.name,
            "stages": {
                "bastion_network": _stage(False, _classify_connection_error(e)),
                "bastion_auth": _stage(False, "未実施（踏み台へのネットワーク到達に失敗したため）"),
            },
            "targets": [],
        }
    except paramiko.SSHException as e:
        return {
            "environment": env.name,
            "stages": {
                "bastion_network": _stage(True),
                "bastion_auth": _stage(False, _classify_connection_error(e)),
            },
            "targets": [],
        }

    with bastion:
        target_results = [_run_target(cfg, env_secrets, bastion, target) for target in env.targets]

    return {
        "environment": env.name,
        "stages": {
            "bastion_network": _stage(True),
            "bastion_auth": _stage(True),
        },
        "targets": target_results,
    }
