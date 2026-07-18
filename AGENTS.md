# AGENTS.md

AIエージェント（Claude Code等）でこのリポジトリを開発する際の前提と約束事。
プロジェクトの背景・要件・設計の詳細は以下を参照（内容をここに複製しない）。

- [README.md](README.md) — セットアップ手順、config.yamlとsecrets.yamlの対応関係
- [files/requirements.md](files/requirements.md) — 要件整理
- [files/config_design.md](files/config_design.md) — 設定ファイル設計
- [files/development_plan.md](files/development_plan.md) — 技術スタック選定理由・マイルストーン

## プロジェクトの制約（変更提案の前に必ず確認）

- **未署名のexeファイルは作らない。** 企業内のEDR/アプリケーションホワイトリストで
  ブロックされるため、承認済みのPython 3.13インタプリタでスクリプトを実行する構成が
  大前提。PyInstaller等によるexe化を提案しないこと。
- **フロントエンドはビルドチェーンなしの素のHTML/CSS/JS。** `static/`配下に置いた
  ファイルをそのまま配信する。React等のフレームワークやnpm/bundlerの導入を提案しないこと。
- **依存パッケージの追加は慎重に。** 社内プロキシ配下でのpip installが前提のため、
  依存は最小限（flask / waitress / paramiko / pyyaml）に保つ。追加する場合は理由を明示する。
- コメント・docstring・コミットメッセージ・画面表示は**日本語**で書く（既存コードのスタイルに合わせる）。

## セキュリティ上の約束事

- `secrets.yaml`・`keys/`配下（`keys/test/`を除く）は**コミット禁止**（.gitignore済み）。
  誤ってステージしないこと。
- `keys/test/` の鍵ペアは**Docker検証環境（docker/testenv）専用**。実環境では絶対に
  使用しない。新しいシークレットのサンプルを追加する場合も実環境の値を書かない。
- チェックや事前処理でシークレットを扱う場合、**コマンド文字列に埋め込まない**。
  対象サーバの`ps`・ログ・API結果に露出するため、標準入力経由で渡す
  （`SSHConnection.run_command`の`stdin_data`、setup_definitionsの`secret_key`の仕組みを使う）。

## 動作確認の方法

実環境の踏み台なしで、SSH多段接続を含めてローカル検証できる。

```
# テスト用の踏み台・対象VMコンテナ群を起動（env-a/env-b、via経由の3段構成を含む）
cd docker/testenv
docker compose up -d --build

# アプリ起動（リポジトリルートで。config.yaml/secrets.yamlは
# docker/testenv/docker-compose.yml冒頭のコメントにある接続情報に合わせて用意する）
python run.py
# → http://localhost:18080/ をブラウザで開く
```

- 接続情報の要点: env-a踏み台=localhost:2222、env-b踏み台=localhost:2223
  （testuser/testpass）、対象VMは`keys/test/`の秘密鍵で接続。
  詳細は [docker/testenv/docker-compose.yml](docker/testenv/docker-compose.yml) 冒頭のコメント参照。
- 対象VMコンテナにはダミーの`oc`/`kubectl`等（docker/testenv/dummy-bin/）が入っており、
  チェック実行まで一通り確認できる。
- 設定の整合性（config.yamlとsecrets.yamlのキー対応、ロール・チェック定義の参照）は
  `python run.py` 起動時に`app/config.py`の`validate()`でまとめて検証され、
  問題箇所が具体的に表示される。
- ルートの`ssh_test.py` / `ssh_multihop_test.py`は手動検証用スクリプト（pytestではない）。

## 設定ファイルの対応関係

`config.yaml`（Git管理対象）と`secrets.yaml`（Git管理外）は名前で対応しており、
片方だけ変更すると起動時エラーになる。対応表はREADMEの
「config.yamlとsecrets.yamlの対応関係」を参照。

## Git運用

- `main`は保護ブランチ。`feat/xxx`等の機能ブランチを切ってPRでマージする。
- コミットメッセージは日本語で、関連Issue番号を`(#N)`形式で付ける
  （例: `oc login等の事前処理をロール単位で実行できるようにする(#7)`）。

## 確定済みの今後の方針（2026-07のレビューより）

改善事項はGitHub Issue（#16〜#23）で管理している。着手前に対象Issueの本文を読むこと。
特に以下は設計方針として確定済みで、関連する実装はこの方針に沿わせる。

- チェック実行は**サーバ側バックグラウンドスレッドで定期実行＋結果キャッシュ**方式へ
  移行する（#17。現状の「/api/statusリクエストごとに同期実行」は暫定）。
- `check_definitions`の`parser`（table / systemd_state / raw_text）はフロントエンドでの
  出力整形に使う（#19。現状は未使用で、生テキスト表示のみ）。
