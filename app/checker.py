"""チェック実行モジュール。

設定内の1つの環境に対して踏み台経由で多段SSH接続し、各対象サーバに
割り当てられたロールのチェックをまとめて実行する。
"""

from __future__ import annotations

from app.config import Config, Secrets, Target
from app.sshclient import SSHConnection


def _check_names_for_target(cfg: Config, target: Target) -> list[str]:
    """対象サーバのrolesから実行すべきチェック名を重複除去した上で返す。"""
    names: list[str] = []
    for role in target.roles:
        for check_name in cfg.roles.get(role, []):
            if check_name not in names:
                names.append(check_name)
    return names


def run_checks(cfg: Config, secrets: Secrets, env_name: str | None = None) -> dict:
    """指定環境（省略時はconfig.yaml先頭の環境）のチェックを実行し、結果を返す。"""
    env = cfg.environments[0]
    if env_name is not None:
        env = next(e for e in cfg.environments if e.name == env_name)

    env_secrets = secrets.environments[env.name]

    target_results = []
    with SSHConnection(
        host=env.bastion.host,
        port=env.bastion.port,
        username=env_secrets.bastion.username,
        password=env_secrets.bastion.password,
    ) as bastion:
        for target in env.targets:
            target_secret = env_secrets.targets[target.name]
            channel = bastion.open_channel_to(target.host, target.port)

            checks = []
            with SSHConnection(
                host=target.host,
                port=target.port,
                username=target_secret.username,
                key_filename=target_secret.private_key_path,
                sock=channel,
            ) as target_conn:
                for check_name in _check_names_for_target(cfg, target):
                    check_def = cfg.check_definitions[check_name]
                    stdout, stderr, exit_status = target_conn.run_command(check_def.command)
                    checks.append(
                        {
                            "name": check_name,
                            "command": check_def.command,
                            "parser": check_def.parser,
                            "exit_status": exit_status,
                            "stdout": stdout,
                            "stderr": stderr,
                        }
                    )

            target_results.append(
                {
                    "name": target.name,
                    "host": target.host,
                    "roles": target.roles,
                    "checks": checks,
                }
            )

    return {
        "environment": env.name,
        "targets": target_results,
    }
