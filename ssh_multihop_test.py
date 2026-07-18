"""M2検証用CLI: 踏み台経由で対象VMに多段SSH接続し、任意コマンドを実行して結果を表示する。"""

import argparse
import sys

from app.sshclient import SSHConnection

sys.stdout.reconfigure(encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="踏み台経由の多段SSH接続テスト")
    parser.add_argument("--bastion-host", required=True)
    parser.add_argument("--bastion-port", type=int, default=22)
    parser.add_argument("--bastion-username", required=True)
    parser.add_argument("--bastion-password", default=None)
    parser.add_argument("--target-host", required=True)
    parser.add_argument("--target-port", type=int, default=22)
    parser.add_argument("--target-username", required=True)
    parser.add_argument("--target-key-filename", default=None)
    parser.add_argument("--command", required=True)
    args = parser.parse_args()

    with SSHConnection(
        host=args.bastion_host,
        port=args.bastion_port,
        username=args.bastion_username,
        password=args.bastion_password,
    ) as bastion:
        channel = bastion.open_channel_to(args.target_host, args.target_port)

        with SSHConnection(
            host=args.target_host,
            port=args.target_port,
            username=args.target_username,
            key_filename=args.target_key_filename,
            sock=channel,
        ) as target:
            stdout, stderr, exit_status = target.run_command(args.command)

    print(f"--- exit_status: {exit_status} ---")
    print("--- stdout ---")
    print(stdout)
    if stderr:
        print("--- stderr ---")
        print(stderr)


if __name__ == "__main__":
    main()
