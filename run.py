"""起動スクリプト。現時点（M0）では config.yaml / secrets.yaml をロードして内容を表示する。"""

import argparse
import sys

from app.config import Config, Secrets, load_config, load_secrets

# Windows環境ではコンソールの実際のコードページとPythonのデフォルトエンコーディングが
# 食い違い、日本語出力が文字化けすることがあるため、明示的にUTF-8へ固定する。
sys.stdout.reconfigure(encoding="utf-8")


def print_summary(cfg: Config, secrets: Secrets) -> None:
    print("=== 環境一覧 ===")
    for env in cfg.environments:
        print(f"- {env.name} (bastion: {env.bastion.host}:{env.bastion.port}, auth_type={env.bastion.auth_type})")

        env_secrets = secrets.environments.get(env.name)
        if env_secrets is None:
            print(f"    ! secrets.yaml に {env.name} の認証情報がありません")
        else:
            print(f"    bastion user: {env_secrets.bastion.username}")

        for target in env.targets:
            print(f"    - {target.name} ({target.host}:{target.port}) roles={target.roles}")

            if env_secrets is not None:
                target_secret = env_secrets.targets.get(target.name)
                if target_secret is None:
                    print(f"        ! secrets.yaml に {target.name} の認証情報がありません")
                else:
                    print(f"        user={target_secret.username} private_key={target_secret.private_key_path}")

    print("\n=== ロール定義 ===")
    for role, checks in cfg.roles.items():
        print(f"- {role}: {checks}")

    print("\n=== チェック定義 ===")
    for name, check_def in cfg.check_definitions.items():
        print(f"- {name}: command={check_def.command!r} parser={check_def.parser}")

    print("\n=== ポーリング設定 ===")
    print(f"interval_seconds={cfg.polling.interval_seconds} auto_refresh={cfg.polling.auto_refresh}")

    print("\n=== Web設定 ===")
    print(f"listen_addr={cfg.web.listen_addr} auth={cfg.web.auth}")


def main() -> None:
    parser = argparse.ArgumentParser(description="infra-status-dashboard")
    parser.add_argument("--config", default="config.yaml", help="config.yaml のパス")
    parser.add_argument("--secrets", default="secrets.yaml", help="secrets.yaml のパス")
    args = parser.parse_args()

    cfg = load_config(args.config)
    secrets = load_secrets(args.secrets)

    print_summary(cfg, secrets)


if __name__ == "__main__":
    main()
