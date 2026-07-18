# infra-status-dashboard

Windows上で、企業内承認済みのPython実行環境を使って動作するサーバアプリケーションから、
踏み台サーバ経由でLinux/Kubernetes/OpenShift環境の稼働状態を確認できるダッシュボード。

未署名・不明なexeファイルの実行はEDR/アプリケーションホワイトリスト等でブロックされる
可能性があるため、単体の実行ファイルは作成せず、承認済みのPythonインタプリタで
スクリプトを実行する構成を採用している。

詳細な要件・設計は以下を参照。

- [files/requirements.md](files/requirements.md)
- [files/config_design.md](files/config_design.md)
- [files/development_plan.md](files/development_plan.md)

## セットアップ

1. Python 3.13をインストールする（承認済み実行環境）。
2. 設定ファイルを用意する。

   ```
   cp config.yaml.example config.yaml
   cp secrets.yaml.example secrets.yaml
   ```

   `config.yaml` は環境・ロール・チェック内容などの定義（Git管理対象）、
   `secrets.yaml` は踏み台のパスワードや秘密鍵パスなどの認証情報
   （`.gitignore`によりGit管理対象外）。内容は環境に合わせて書き換える。

3. 仮想環境を作成し、依存パッケージをインストールする。

   ```
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

## 実行

```
python run.py
```

デフォルトでは `./config.yaml` / `./secrets.yaml` を読み込む。パスを変更する場合：

```
python run.py --config path/to/config.yaml --secrets path/to/secrets.yaml
```

現時点（M0）では、設定ファイルをロードして内容をCLIに表示するのみ。
SSH接続・HTTPサーバ・フロントエンドは今後のマイルストーンで実装する
（[development_plan.md](files/development_plan.md) 参照）。

`start.bat`をダブルクリックすると、初回は`.venv`の作成・依存パッケージのインストールを
自動で行い、以降は`.venv`を有効化した上で`run.py`を起動する。
