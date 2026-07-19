"""起動スクリプト。config.yaml / secrets.yaml をロードし、Flask + waitressでREST APIサーバを起動する。"""

import argparse
import logging
import sys

from waitress import serve

from app.config import ConfigError, load_config, load_secrets, validate
from app.server import create_app

sys.stdout.reconfigure(encoding="utf-8")

# logging.basicConfig()は既定でsys.stderrに出力するが、上記でUTF-8化したのは
# sys.stdoutのみのため、ログの出力先も明示的にsys.stdoutへ合わせる
# （合わせないと日本語メッセージが元のコンソールエンコーディングで文字化けする）。
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)


def resolve_listen_addr(listen_addr: str) -> tuple[str, int]:
    """config.yamlの \":8080\" 形式の待受アドレスを (host, port) に変換する。"""
    host, _, port_str = listen_addr.rpartition(":")
    return host or "0.0.0.0", int(port_str)


def main() -> None:
    parser = argparse.ArgumentParser(description="infra-status-dashboard server")
    parser.add_argument("--config", default="config.yaml", help="config.yaml のパス")
    parser.add_argument("--secrets", default="secrets.yaml", help="secrets.yaml のパス")
    args = parser.parse_args()

    try:
        cfg = load_config(args.config)
        secrets = load_secrets(args.secrets)
    except (ConfigError, FileNotFoundError, KeyError) as e:
        print(f"[ERROR] 設定ファイルの読み込みに失敗しました: {e}")
        sys.exit(1)

    problems = validate(cfg, secrets)
    if problems:
        print("[ERROR] config.yaml / secrets.yamlに以下の問題があります。修正してから起動してください。")
        for problem in problems:
            print(f"  - {problem}")
        sys.exit(1)

    host, port = resolve_listen_addr(cfg.web.listen_addr)

    app = create_app(cfg, secrets)
    print(f"Listening on {host}:{port}")
    serve(app, host=host, port=port)


if __name__ == "__main__":
    main()
