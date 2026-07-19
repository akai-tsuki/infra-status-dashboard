"""app/config.py のユニットテスト（Issue #22）。

SSH接続を伴う部分（load_config/load_secretsが返す値を実際に使っての接続）は
docker/testenvでの統合確認の対象とし、ここでは辞書からのビルドと
validate()の整合性チェックのみを対象にする。
"""

import copy

import pytest

from app.config import Bastion, ConfigError, Config, Environment, Secrets, Target, TargetSecret, validate


def _base_config_dict() -> dict:
    """validate()が問題なしと判定する最小構成のconfig.yaml相当の辞書を返す。"""
    return {
        "environments": [
            {
                "name": "env-a",
                "bastion": {"host": "bastion.example.local", "port": 22, "auth_type": "password"},
                "targets": [
                    {"name": "vm-a", "host": "10.0.0.1", "port": 22, "roles": ["role-a"]},
                ],
            }
        ],
        "roles": {"role-a": ["check-a"]},
        "check_definitions": {"check-a": {"command": "echo hi", "parser": "raw_text"}},
        "polling": {"interval_seconds": 60, "auto_refresh": True},
        "web": {"listen_addr": ":18080", "auth": "none"},
    }


def _base_secrets_dict() -> dict:
    """_base_config_dict()に対応する、認証情報の欠落がない最小構成のsecrets.yaml相当の辞書を返す。"""
    return {
        "environments": {
            "env-a": {
                "bastion": {"username": "bastion-user", "password": "bastion-pass"},
                "targets": {
                    "vm-a": {"username": "vm-user", "private_key_path": "keys/vm-a.key"},
                },
            }
        }
    }


def _build(config_dict: dict, secrets_dict: dict) -> tuple[Config, Secrets]:
    return Config.from_dict(config_dict), Secrets.from_dict(secrets_dict)


class TestFromDictDefaults:
    """省略可能フィールドのデフォルト値の確認。"""

    def test_bastion_default_port(self):
        bastion = Bastion.from_dict({"host": "h", "auth_type": "password"})
        assert bastion.port == 22

    def test_target_defaults(self):
        target = Target.from_dict({"name": "n", "host": "h"})
        assert target.port == 22
        assert target.roles == []
        assert target.via is None

    def test_environment_missing_bastion_raises_config_error(self):
        with pytest.raises(ConfigError):
            Environment.from_dict({"name": "env-x", "targets": []})

    def test_config_role_setup_and_setup_definitions_default_to_empty(self):
        cfg = Config.from_dict(_base_config_dict())
        assert cfg.role_setup == {}
        assert cfg.setup_definitions == {}

    def test_config_environments_default_to_empty_list(self):
        d = _base_config_dict()
        del d["environments"]
        cfg = Config.from_dict(d)
        assert cfg.environments == []

    def test_secrets_from_empty_dict(self):
        assert Secrets.from_dict({}).environments == {}

    def test_target_secret_setup_secrets_defaults_to_empty(self):
        secret = TargetSecret.from_dict({"username": "u", "private_key_path": "p"})
        assert secret.setup_secrets == {}


class TestValidate:
    """validate()の正常系・各不整合パターン。"""

    def test_no_problems_for_base_config(self):
        cfg, secrets = _build(_base_config_dict(), _base_secrets_dict())
        assert validate(cfg, secrets) == []

    def test_missing_env_secrets(self):
        secrets_dict = _base_secrets_dict()
        del secrets_dict["environments"]["env-a"]
        cfg, secrets = _build(_base_config_dict(), secrets_dict)

        problems = validate(cfg, secrets)

        assert len(problems) == 1
        assert "env-a" in problems[0]
        assert "認証情報がありません" in problems[0]

    def test_missing_target_secrets(self):
        secrets_dict = _base_secrets_dict()
        del secrets_dict["environments"]["env-a"]["targets"]["vm-a"]
        cfg, secrets = _build(_base_config_dict(), secrets_dict)

        problems = validate(cfg, secrets)

        assert any("vm-a" in p and "認証情報がありません" in p for p in problems)

    def test_undefined_role(self):
        config_dict = _base_config_dict()
        config_dict["environments"][0]["targets"][0]["roles"] = ["role-undefined"]
        cfg, secrets = _build(config_dict, _base_secrets_dict())

        problems = validate(cfg, secrets)

        assert any("role-undefined" in p and "rolesに定義されていません" in p for p in problems)

    def test_undefined_check(self):
        config_dict = _base_config_dict()
        config_dict["roles"]["role-a"] = ["check-undefined"]
        cfg, secrets = _build(config_dict, _base_secrets_dict())

        problems = validate(cfg, secrets)

        assert any("check-undefined" in p and "check_definitionsに定義されていません" in p for p in problems)

    def test_via_target_not_found(self):
        config_dict = _base_config_dict()
        config_dict["environments"][0]["targets"][0]["via"] = "no-such-target"
        cfg, secrets = _build(config_dict, _base_secrets_dict())

        problems = validate(cfg, secrets)

        assert any("no-such-target" in p and "同じ環境のtargetsに存在しません" in p for p in problems)

    def test_via_cycle_detected(self):
        config_dict = _base_config_dict()
        config_dict["environments"][0]["targets"] = [
            {"name": "vm-a", "host": "10.0.0.1", "roles": [], "via": "vm-b"},
            {"name": "vm-b", "host": "10.0.0.2", "roles": [], "via": "vm-a"},
        ]
        secrets_dict = _base_secrets_dict()
        secrets_dict["environments"]["env-a"]["targets"] = {
            "vm-a": {"username": "u", "private_key_path": "k"},
            "vm-b": {"username": "u", "private_key_path": "k"},
        }
        cfg, secrets = _build(config_dict, secrets_dict)

        problems = validate(cfg, secrets)

        assert any("循環参照" in p for p in problems)

    def test_via_self_reference_is_a_cycle(self):
        config_dict = _base_config_dict()
        config_dict["environments"][0]["targets"][0]["via"] = "vm-a"
        cfg, secrets = _build(config_dict, _base_secrets_dict())

        problems = validate(cfg, secrets)

        assert any("循環参照" in p for p in problems)

    def test_role_setup_undefined_setup(self):
        config_dict = _base_config_dict()
        config_dict["role_setup"] = {"role-a": ["setup-undefined"]}
        cfg, secrets = _build(config_dict, _base_secrets_dict())

        problems = validate(cfg, secrets)

        assert any("setup-undefined" in p and "setup_definitionsに定義されていません" in p for p in problems)

    def test_missing_setup_secret(self):
        config_dict = _base_config_dict()
        config_dict["role_setup"] = {"role-a": ["login"]}
        config_dict["setup_definitions"] = {
            "login": {"command": "read TOKEN && login --token=$TOKEN", "secret_key": "token"}
        }
        cfg, secrets = _build(config_dict, _base_secrets_dict())

        problems = validate(cfg, secrets)

        assert any(
            "vm-a" in p and "token" in p and "setup_secrets" in p and "ありません" in p for p in problems
        )

    def test_setup_secret_present_is_not_a_problem(self):
        config_dict = _base_config_dict()
        config_dict["role_setup"] = {"role-a": ["login"]}
        config_dict["setup_definitions"] = {
            "login": {"command": "read TOKEN && login --token=$TOKEN", "secret_key": "token"}
        }
        secrets_dict = _base_secrets_dict()
        secrets_dict["environments"]["env-a"]["targets"]["vm-a"]["setup_secrets"] = {"token": "dummy"}
        cfg, secrets = _build(config_dict, secrets_dict)

        assert validate(cfg, secrets) == []

    @pytest.mark.parametrize("auth_type", ["key", "publickey", ""])
    def test_unsupported_bastion_auth_type(self, auth_type):
        config_dict = _base_config_dict()
        config_dict["environments"][0]["bastion"]["auth_type"] = auth_type
        cfg, secrets = _build(config_dict, _base_secrets_dict())

        problems = validate(cfg, secrets)

        assert any("bastion.auth_type" in p and "password" in p for p in problems)

    @pytest.mark.parametrize("web_auth", ["basic", "token", ""])
    def test_unsupported_web_auth(self, web_auth):
        config_dict = _base_config_dict()
        config_dict["web"]["auth"] = web_auth
        cfg, secrets = _build(config_dict, _base_secrets_dict())

        problems = validate(cfg, secrets)

        assert any("web.auth" in p and "none" in p for p in problems)

    def test_multiple_problems_are_all_reported(self):
        """1箇所直しても他の問題は見逃されない（起動時にまとめて表示する設計の確認）。"""
        config_dict = _base_config_dict()
        config_dict["environments"][0]["targets"][0]["roles"] = ["role-undefined"]
        config_dict["web"]["auth"] = "basic"
        cfg, secrets = _build(config_dict, _base_secrets_dict())

        problems = validate(cfg, secrets)

        assert len(problems) == 2

    def test_does_not_mutate_input(self):
        """validate()は読み取り専用であるべき（config_dictを2回使う他のテストの前提を守るための確認）。"""
        config_dict = _base_config_dict()
        secrets_dict = _base_secrets_dict()
        cfg, secrets = _build(config_dict, secrets_dict)
        before = copy.deepcopy(cfg)

        validate(cfg, secrets)

        assert cfg == before
