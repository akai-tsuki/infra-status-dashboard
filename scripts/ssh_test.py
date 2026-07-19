"""M1検証用CLI: 踏み台に1段SSH接続し、任意コマンドを実行して結果を表示する。

scripts/配下からの実行でもリポジトリルートのappパッケージをimportできるよう、
リポジトリルートをsys.pathへ追加してから import する。
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.sshclient import SSHConnection  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="踏み台への単純SSH接続テスト")
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", default=None)
    parser.add_argument("--key-filename", default=None)
    parser.add_argument("--command", required=True)
    args = parser.parse_args()

    with SSHConnection(
        host=args.host,
        port=args.port,
        username=args.username,
        password=args.password,
        key_filename=args.key_filename,
    ) as conn:
        stdout, stderr, exit_status = conn.run_command(args.command)

    print(f"--- exit_status: {exit_status} ---")
    print("--- stdout ---")
    print(stdout)
    if stderr:
        print("--- stderr ---")
        print(stderr)


if __name__ == "__main__":
    main()
