"""config.yaml / secrets.yaml のロードを担当するモジュール。"""

from __future__ import annotations

from dataclasses import dataclass, field

import yaml


class ConfigError(Exception):
    """config.yaml / secrets.yamlの構造・整合性に問題がある場合に送出する。"""


@dataclass
class Bastion:
    host: str
    port: int
    auth_type: str

    @classmethod
    def from_dict(cls, d: dict) -> "Bastion":
        """config.yamlのbastionセクションの辞書からBastionを組み立てる。"""
        return cls(host=d["host"], port=d.get("port", 22), auth_type=d["auth_type"])


@dataclass
class Target:
    name: str
    host: str
    port: int
    roles: list[str]
    via: str | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "Target":
        """config.yamlのtargets[]の1要素の辞書からTargetを組み立てる。"""
        return cls(
            name=d["name"],
            host=d["host"],
            port=d.get("port", 22),
            roles=d.get("roles", []),
            via=d.get("via"),
        )


@dataclass
class Environment:
    name: str
    bastion: Bastion
    targets: list[Target]

    @classmethod
    def from_dict(cls, d: dict) -> "Environment":
        """config.yamlのenvironments[]の1要素の辞書からEnvironmentを組み立てる。

        bastionセクションが無い場合は、生のKeyErrorではなくConfigErrorを
        送出し、どの環境の設定が問題かを分かるようにする。
        """
        name = d.get("name", "(name未設定)")
        if "bastion" not in d:
            raise ConfigError(f"config.yamlのenvironments「{name}」にbastionセクションがありません")
        return cls(
            name=name,
            bastion=Bastion.from_dict(d["bastion"]),
            targets=[Target.from_dict(t) for t in d.get("targets", [])],
        )


@dataclass
class CheckDefinition:
    command: str
    parser: str

    @classmethod
    def from_dict(cls, d: dict) -> "CheckDefinition":
        """config.yamlのcheck_definitions内の1エントリからCheckDefinitionを組み立てる。"""
        return cls(command=d["command"], parser=d["parser"])


@dataclass
class SetupDefinition:
    command: str
    secret_key: str | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "SetupDefinition":
        """config.yamlのsetup_definitions内の1エントリからSetupDefinitionを組み立てる。"""
        return cls(command=d["command"], secret_key=d.get("secret_key"))


@dataclass
class Polling:
    interval_seconds: int
    auto_refresh: bool

    @classmethod
    def from_dict(cls, d: dict) -> "Polling":
        """config.yamlのpollingセクションの辞書からPollingを組み立てる。"""
        return cls(interval_seconds=d["interval_seconds"], auto_refresh=d["auto_refresh"])


@dataclass
class Web:
    listen_addr: str
    auth: str

    @classmethod
    def from_dict(cls, d: dict) -> "Web":
        """config.yamlのwebセクションの辞書からWebを組み立てる。"""
        return cls(listen_addr=d["listen_addr"], auth=d["auth"])


@dataclass
class Config:
    environments: list[Environment]
    roles: dict[str, list[str]]
    check_definitions: dict[str, CheckDefinition]
    polling: Polling
    web: Web
    role_setup: dict[str, list[str]] = field(default_factory=dict)
    setup_definitions: dict[str, SetupDefinition] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "Config":
        """config.yaml全体の辞書（yaml.safe_loadの結果）からConfigを組み立てる。"""
        return cls(
            environments=[Environment.from_dict(e) for e in d.get("environments", [])],
            roles=d.get("roles", {}),
            check_definitions={
                name: CheckDefinition.from_dict(v) for name, v in d.get("check_definitions", {}).items()
            },
            polling=Polling.from_dict(d["polling"]),
            web=Web.from_dict(d["web"]),
            role_setup=d.get("role_setup", {}),
            setup_definitions={
                name: SetupDefinition.from_dict(v) for name, v in d.get("setup_definitions", {}).items()
            },
        )


@dataclass
class BastionSecret:
    username: str
    password: str

    @classmethod
    def from_dict(cls, d: dict) -> "BastionSecret":
        """secrets.yamlのbastionセクションの辞書からBastionSecretを組み立てる。"""
        return cls(username=d["username"], password=d["password"])


@dataclass
class TargetSecret:
    username: str
    private_key_path: str
    setup_secrets: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "TargetSecret":
        """secrets.yamlのtargets内の1エントリからTargetSecretを組み立てる。"""
        return cls(
            username=d["username"],
            private_key_path=d["private_key_path"],
            setup_secrets=d.get("setup_secrets", {}),
        )


@dataclass
class EnvSecrets:
    bastion: BastionSecret
    targets: dict[str, TargetSecret]

    @classmethod
    def from_dict(cls, d: dict) -> "EnvSecrets":
        """secrets.yamlのenvironments内の1環境分の辞書からEnvSecretsを組み立てる。"""
        return cls(
            bastion=BastionSecret.from_dict(d["bastion"]),
            targets={name: TargetSecret.from_dict(v) for name, v in d.get("targets", {}).items()},
        )


@dataclass
class Secrets:
    environments: dict[str, EnvSecrets] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "Secrets":
        """secrets.yaml全体の辞書（yaml.safe_loadの結果）からSecretsを組み立てる。"""
        return cls(
            environments={name: EnvSecrets.from_dict(v) for name, v in d.get("environments", {}).items()}
        )


def load_config(path: str) -> Config:
    """指定パスのconfig.yamlを読み込みConfigを返す。"""
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return Config.from_dict(data)


def load_secrets(path: str) -> Secrets:
    """指定パスのsecrets.yamlを読み込みSecretsを返す。"""
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return Secrets.from_dict(data)


def _has_via_cycle(target: Target, targets_by_name: dict[str, "Target"]) -> bool:
    """target.viaを辿っていったときに循環参照になっていないかを調べる。"""
    seen = {target.name}
    current = target
    while current.via is not None:
        if current.via not in targets_by_name or current.via in seen:
            return current.via in seen
        seen.add(current.via)
        current = targets_by_name[current.via]
    return False


def validate(cfg: Config, secrets: Secrets) -> list[str]:
    """config.yamlとsecrets.yaml間、およびconfig.yaml内部の対応関係を検証する。

    問題があった箇所を示す文字列のリストを返す（問題がなければ空リスト）。
    起動時にまとめて検証することで、KeyError等の分かりにくいエラーで
    落ちる前に、設定のどこを直すべきかを利用者に提示できるようにする。
    """
    problems: list[str] = []

    for env in cfg.environments:
        env_secrets = secrets.environments.get(env.name)
        if env_secrets is None:
            problems.append(
                f"secrets.yamlにconfig.yamlのenvironments「{env.name}」に対応する認証情報がありません"
            )
            continue

        targets_by_name = {t.name: t for t in env.targets}

        for target in env.targets:
            if target.name not in env_secrets.targets:
                problems.append(
                    f"secrets.yamlの環境「{env.name}」に対象サーバ「{target.name}」の認証情報がありません"
                )

            target_secret = env_secrets.targets.get(target.name)

            for role in target.roles:
                if role not in cfg.roles:
                    problems.append(
                        f"config.yamlのenvironments「{env.name}」の対象サーバ「{target.name}」が"
                        f"参照しているロール「{role}」がrolesに定義されていません"
                    )

                for setup_name in cfg.role_setup.get(role, []):
                    setup_def = cfg.setup_definitions.get(setup_name)
                    if setup_def is None:
                        # setup_definitionsの欠落自体は下のrole_setupループでまとめて報告する
                        continue
                    if setup_def.secret_key is not None and target_secret is not None:
                        if setup_def.secret_key not in target_secret.setup_secrets:
                            problems.append(
                                f"secrets.yamlの対象サーバ「{target.name}」にsetup_secrets"
                                f"「{setup_def.secret_key}」がありません"
                                f"（事前処理「{setup_name}」で必要）"
                            )

            if target.via is not None:
                if target.via not in targets_by_name:
                    problems.append(
                        f"config.yamlのenvironments「{env.name}」の対象サーバ「{target.name}」が"
                        f"経由先として指定しているvia「{target.via}」が同じ環境のtargetsに存在しません"
                    )
                elif _has_via_cycle(target, targets_by_name):
                    problems.append(
                        f"config.yamlのenvironments「{env.name}」の対象サーバ「{target.name}」の"
                        f"viaが循環参照になっています"
                    )

    for role, check_names in cfg.roles.items():
        for check_name in check_names:
            if check_name not in cfg.check_definitions:
                problems.append(
                    f"config.yamlのroles「{role}」が参照しているチェック「{check_name}」が"
                    f"check_definitionsに定義されていません"
                )

    for role, setup_names in cfg.role_setup.items():
        for setup_name in setup_names:
            if setup_name not in cfg.setup_definitions:
                problems.append(
                    f"config.yamlのrole_setup「{role}」が参照している事前処理「{setup_name}」が"
                    f"setup_definitionsに定義されていません"
                )

    return problems
