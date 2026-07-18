# 開発計画

## 0. 方針転換の経緯

当初はGoによるシングルバイナリ（`server.exe`）配布を想定していたが、企業内では
**未署名・不明なexeファイルの実行がEDR/アプリケーションホワイトリスト等でブロック
される**懸念があるため、方針を変更する。

対象のWindowsマシンには**企業で承認済みのPython環境**がすでに導入されているため、
新規に不明な実行ファイルを作らず、**承認済みのpython.exeでスクリプトを実行する**
形に変更する。

## 1. 技術スタック（改訂版）

| 領域 | 選定 | 理由 |
|---|---|---|
| 言語 | Python 3.13 | 企業内で承認済みの実行環境を利用でき、新規の未署名exeを作らずに済む |
| SSH | `paramiko` | 多段SSH接続（踏み台→対象VM）をコード上で制御しやすい。Pythonでの定番SSHライブラリ |
| 設定ファイル | `PyYAML` | config.yaml / secrets.yaml のパース |
| Webフレームワーク | `Flask` | 軽量でREST API・静的ファイル配信ともに実装しやすい |
| 本番向けWAIサーバ | `waitress` | FlaskのビルトインサーバはPython開発用のため、Windowsでも動く`waitress`を本番実行に使う |
| バックグラウンドポーリング | 標準 `threading` | 一定間隔でのチェック実行・一時停止・手動更新をシンプルなスレッド管理で実現 |
| フロントエンド実装 | 素のHTML/CSS/JS（軽量） | ビルドチェーンを増やさず、`static/`配下にそのまま配置するだけで完結させる |

**確定事項**：Pythonバージョンは3.13、`pip install`可能、`.bat`からの起動可能、
Windowsサービス化は不要（詳細はTODOセクション参照）。

## 2. リポジトリ構成（改訂版）

```
repo/
├── app/
│   ├── __init__.py
│   ├── config.py                # config.yaml / secrets.yaml のロード・マージ
│   ├── sshclient.py              # 踏み台経由の多段SSH接続管理（paramiko）
│   ├── checker.py                # チェック実行・結果の保持（キャッシュ）・バックグラウンドポーリング
│   ├── api.py                    # Flask Blueprint（REST API）
│   └── server.py                 # Flaskアプリ本体
├── static/
│   ├── index.html
│   ├── app.js
│   └── style.css
├── config.yaml.example           # サンプル（実ファイルはGit管理外）
├── secrets.yaml.example          # サンプル（実ファイルはGit管理外）
├── requirements.txt              # flask, waitress, paramiko, pyyaml 等
├── run.py                        # 起動スクリプト（`python run.py`で起動）
├── start.bat                     # ダブルクリックで起動用（venv作成・依存インストール・起動をまとめて実行）
├── .gitignore
└── README.md
```

## 3. マイルストーン（実装順序・改訂版）

Go版と同様、技術的リスクが高い部分（SSH多段接続）を先に潰す順番は変更しない。

| # | 内容 | ゴール |
|---|---|---|
| M0 | プロジェクト雛形作成 | `requirements.txt`整備、config.yaml/secrets.yamlをロードしてCLIに表示できる |
| M1 | 踏み台への単純SSH接続 | `paramiko`で踏み台に1段SSH接続し、任意コマンドを実行して結果を標準出力に表示できる |
| M2 | 多段SSH接続 | 踏み台経由で対象VMに接続し、`kubectl get nodes`・`oc get co`等の実コマンドが取得できることを確認する（**最重要検証ポイント**） |
| M3 | HTTPサーバ化 | Flask + waitressでREST APIを立て、チェック結果をJSON返却できる（1環境のみ、手動リクエストベース） |
| M4 | フロントエンド実装 | ダッシュボード画面でチェック結果を表示。ポーリング・一時停止・手動更新を実装 |
| M5 | 複数環境対応 | `environments`の切り替えUI・切り替え時のSSH接続の張り替えを実装 |
| M6 | エラーハンドリング強化 | 接続失敗・タイムアウト・sudo失敗等を画面に分かりやすく表示 |
| M7 | 配布パッケージの整備 | `venv`構築手順・起動方法（`python run.py`）をREADMEに整理し、実機（社内承認済みPython環境）で動作確認する。exe化は行わない |

## 4. GitHub運用

- **ブランチ戦略**：`main`を保護ブランチとし、機能単位で`feature/xxx`ブランチを作成してPRでマージ
- **Issue／マイルストーン**：上記M0〜M7をGitHubのMilestoneとして登録し、各タスクをIssue化
- **.gitignore**：以下を除外する
  ```
  secrets.yaml
  keys/
  .venv/
  __pycache__/
  *.pyc
  ```
- **サンプルファイル**：`config.yaml.example` / `secrets.yaml.example` をリポジトリに含め、READMEで案内する
- **README.md**：セットアップ手順（`venv`作成、`pip install -r requirements.txt`、`python run.py`での起動）を最初に整備しておく

## 5. 配布・起動方法

- Pythonが承認済み環境なので、**リポジトリをそのままクローン（またはzip配布）し、
  ローカルで`venv`を作成して依存パッケージをインストールする**運用とする
  ```
  python -m venv .venv
  .venv\Scripts\activate
  pip install -r requirements.txt
  python run.py
  ```
- `.bat`ファイルからのPython実行が許容されているため、**利用者は`start.bat`を
  ダブルクリックするだけで起動できる**ようにする。`start.bat`は、初回は
  `venv`未作成なら作成＋依存インストールを行い、以降は`venv`を有効化して
  `python run.py`を実行する、という内容にする想定
  ```bat
  @echo off
  if not exist .venv (
      python -m venv .venv
      call .venv\Scripts\activate.bat
      pip install -r requirements.txt
  ) else (
      call .venv\Scripts\activate.bat
  )
  python run.py
  ```

## 6. テストの考え方

- **SSH接続部分**：モックが難しいため、ローカルにDockerでSSHサーバコンテナ（テスト用の`sshd`）を1〜2台立てて、`paramiko`を使った多段接続・コマンド実行の統合テストを行う構成が現実的
- **チェック結果のパーサー部分**（`table`/`raw_text`/`systemd_state`/`json`）：`pytest`で入力と期待する構造化結果のペアをユニットテストする
- **config/secretsのロード処理**：YAMLのパース・マージロジックもユニットテスト対象にしやすい

## 7. 最初の一歩

まずは **M0〜M2**（プロジェクト雛形 → 踏み台への単純SSH接続 → 多段SSH接続での実コマンド実行）から着手するのがお勧め。ここが動けば、以降のHTTPサーバ化・UI実装は比較的定型的な作業になる。

## 8. 今後確認が必要な事項（TODO）

- [x] `pip install`が可能か → **可能**
- [x] 起動方法として`.bat`スクリプトの配布が許容されるか → **許容される**（`start.bat`から起動する構成に決定）
- [x] 社内で承認されているPythonのバージョン → **Python 3.13**（3.14への変更も可能だが、まずは3.13を採用）
- [x] Windowsサービスとして常駐させたい場合の方式 → **不要**。`start.bat`を起動している間だけ動作する運用でよい（ウィンドウを閉じると停止する点は許容）
