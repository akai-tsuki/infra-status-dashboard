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

対象サーバによっては、踏み台から直接ではなく、別の対象サーバ（コマンド
実行用VM等）を経由しないと到達できない場合がある。targets[].viaで
経由先の対象サーバ名を指定すると、踏み台→(via)→対象サーバの順に
チャネルを継ぎ足して接続する（viaはさらに別のviaを持てるため、理論上は
何段でも辿れる）。
"""

from __future__ import annotations

import socket
from contextlib import ExitStack

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
        # 多段接続で、手前のホップから次のホップへのTCP到達に失敗した場合
        return f"到達に失敗しました（DNS解決失敗・接続拒否等）: {e}"
    if isinstance(e, paramiko.AuthenticationException):
        return f"認証に失敗しました: {e}"
    if isinstance(e, paramiko.SSHException):
        return f"SSH接続に失敗しました: {e}"
    return f"接続に失敗しました: {e}"


def _stage(ok: bool, message: str | None = None) -> dict:
    """1段階分のステータス（成否とメッセージ）を表す辞書を組み立てる。"""
    return {"ok": ok, "message": message}


def _check_names_for_target(cfg: Config, target: Target) -> list[str]:
    """対象サーバのrolesから実行すべきチェック名を重複除去した上で返す。"""
    names: list[str] = []
    for role in target.roles:
        for check_name in cfg.roles.get(role, []):
            if check_name not in names:
                names.append(check_name)
    return names


def _build_hop_chain(target: Target, targets_by_name: dict[str, Target]) -> list[Target]:
    """踏み台に近い方から並べた、targetまでの経由ホップ列を返す（target自身を含む）。"""
    chain = [target]
    current = target
    while current.via is not None:
        current = targets_by_name[current.via]
        chain.append(current)
    chain.reverse()
    return chain


def _connect_chain(
    stack: ExitStack, secrets_for_env, bastion: SSHConnection, chain: list[Target]
) -> tuple[SSHConnection | None, str | None, str | None]:
    """踏み台から順にchainの各ホップへ接続する。

    成功時は (最終ホップへの接続, None, None) を返す。途中で失敗した場合は
    (None, 失敗したホップ名, エラーメッセージ) を返す。
    """
    conn = bastion
    for hop in chain:
        secret = secrets_for_env.targets.get(hop.name)
        if secret is None:
            return None, hop.name, f"secrets.yamlに「{hop.name}」の認証情報がありません"

        try:
            channel = conn.open_channel_to(hop.host, hop.port)
            conn = stack.enter_context(
                SSHConnection(
                    host=hop.host,
                    port=hop.port,
                    username=secret.username,
                    key_filename=secret.private_key_path,
                    sock=channel,
                )
            )
        except CONNECTION_ERRORS as e:
            return None, hop.name, _classify_connection_error(e)

    return conn, None, None


def _run_target_checks(cfg: Config, target: Target, target_conn: SSHConnection) -> list[dict]:
    """接続済みの対象サーバに対し、割り当てられた全チェックを実行し結果を返す。

    チェック単位の実行失敗（コマンドが例外を投げた場合。非ゼロ終了コード
    自体は正常応答として扱い、ここでは失敗にしない）は、他のチェックに
    影響させず"error"フィールドとして個別の結果に含める。
    """
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


def _run_target(
    cfg: Config,
    secrets_for_env,
    bastion: SSHConnection,
    target: Target,
    targets_by_name: dict[str, Target],
) -> dict:
    """1台の対象サーバについて、viaを辿って接続した上で全チェックを実行する。

    経路上のいずれかのホップへの接続に失敗した場合は、チェックを実行せず
    target_connectステージを失敗として返す（他の対象サーバの結果には
    影響しない）。
    """
    chain = _build_hop_chain(target, targets_by_name)

    with ExitStack() as stack:
        target_conn, failed_hop, message = _connect_chain(stack, secrets_for_env, bastion, chain)

        if target_conn is None:
            if failed_hop != target.name:
                message = f"中継サーバ「{failed_hop}」への接続に失敗しました: {message}"
            return {
                "name": target.name,
                "host": target.host,
                "roles": target.roles,
                "stages": {"target_connect": _stage(False, message)},
                "checks": [],
            }

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

    targets_by_name = {t.name: t for t in env.targets}

    with bastion:
        target_results = [
            _run_target(cfg, env_secrets, bastion, target, targets_by_name) for target in env.targets
        ]

    return {
        "environment": env.name,
        "stages": {
            "bastion_network": _stage(True),
            "bastion_auth": _stage(True),
        },
        "targets": target_results,
    }
