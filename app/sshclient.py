"""踏み台サーバ・対象サーバへのSSH接続を管理するモジュール。"""

from __future__ import annotations

import paramiko


class SSHConnection:
    """1段のSSH接続（ID/パスワードまたは秘密鍵認証）を保持するラッパー。"""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str | None = None,
        key_filename: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._client = paramiko.SSHClient()
        # 社内LAN限定運用かつknown_hostsの事前配布が前提にないため、簡易的に
        # 未知ホストキーを自動登録する。中間者攻撃のリスクがあるため、将来的には
        # 既知ホストキーの検証方式への強化を検討する。
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self._client.connect(
            host,
            port=port,
            username=username,
            password=password,
            key_filename=key_filename,
            timeout=timeout,
        )

    def run_command(self, command: str, timeout: float = 30.0) -> tuple[str, str, int]:
        """コマンドを実行し、(stdout, stderr, exit_status) を返す。"""
        _, stdout, stderr = self._client.exec_command(command, timeout=timeout)
        exit_status = stdout.channel.recv_exit_status()
        return stdout.read().decode(errors="replace"), stderr.read().decode(errors="replace"), exit_status

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "SSHConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
