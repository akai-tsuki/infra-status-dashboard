"""起動スクリプト。config.yaml / secrets.yaml をロードし、Flask + waitressでREST APIサーバを起動する。"""

import argparse

from waitress import serve

from app.config import load_config, load_secrets
from app.server import create_app


def resolve_listen_addr(listen_addr: str) -> tuple[str, int]:
    """config.yamlの \":8080\" 形式の待受アドレスを (host, port) に変換する。"""
    host, _, port_str = listen_addr.rpartition(":")
    return host or "0.0.0.0", int(port_str)


def main() -> None:
    parser = argparse.ArgumentParser(description="infra-status-dashboard server")
    parser.add_argument("--config", default="config.yaml", help="config.yaml のパス")
    parser.add_argument("--secrets", default="secrets.yaml", help="secrets.yaml のパス")
    args = parser.parse_args()

    cfg = load_config(args.config)
    secrets = load_secrets(args.secrets)

    host, port = resolve_listen_addr(cfg.web.listen_addr)

    app = create_app(cfg, secrets)
    print(f"Listening on {host}:{port}")
    serve(app, host=host, port=port)


if __name__ == "__main__":
    main()
