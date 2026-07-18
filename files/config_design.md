# 設定ファイル設計（config.yaml）

## 全体構成

```yaml
# ---------------------------------------------------
# 1. 環境一覧（Kubernetes/OpenShift+VM群のセットを環境単位でグループ化）
# ---------------------------------------------------
environments:
  - name: env-a                     # 画面の環境切り替えセレクタに表示される識別名
    bastion:
      host: bastion-a.example.local
      port: 22
      auth_type: password           # secrets.yaml側の認証情報の種類と対応させる

    targets:
      - name: openshift-cmd-vm          # 画面表示用の識別名。secrets.yaml側でもこの名前をキーに使う
        host: 10.0.0.10
        port: 22
        roles: [openshift]

      - name: sample-vm01
        host: 10.0.0.20
        port: 22
        roles: [sample_role_a]

      # 1台のVMで複数の役割を兼ねる場合は roles に複数指定する
      - name: sample-vm02
        host: 10.0.0.21
        roles: [sample_role_b]

  - name: env-b                     # 2つ目の環境。構造はenv-aと同じ
    bastion:
      host: bastion-b.example.local
      port: 22
      auth_type: password

    targets:
      - name: k8s-cmd-vm                # 素のKubernetesクラスタの例（envによって役割を選べることを示す）
        host: 10.1.0.10
        roles: [kubernetes]

      - name: sample-vm01
        host: 10.1.0.20
        roles: [sample_role_a]

# ---------------------------------------------------
# 2. ロール定義（roleごとに実行するチェックのリスト）※全環境で共通
# ---------------------------------------------------
roles:
  kubernetes:
    - kubectl_get_node
    - kubectl_get_pods

  openshift:
    - oc_get_node
    - oc_get_pods
    - oc_get_co
    - oc_get_mcp

  sample_role_a:
    - sample_check_1

  sample_role_b:
    - sample_check_2
    - sample_check_3

# ---------------------------------------------------
# 3. チェック定義（実行コマンドとパース方法）※全環境で共通
# ---------------------------------------------------
check_definitions:
  kubectl_get_node:
    command: "kubectl get nodes -o wide"
    parser: table

  kubectl_get_pods:
    command: "kubectl get pods -A"
    parser: table

  oc_get_node:
    command: "oc get nodes -o wide"
    parser: table

  oc_get_pods:
    command: "oc get pods -A"
    parser: table

  oc_get_co:
    command: "oc get co"
    parser: table

  oc_get_mcp:
    command: "oc get mcp"
    parser: table

  sample_check_1:
    command: "sample-status-command"        # 例: sudo権限が必要なステータス確認コマンド等
    parser: raw_text

  sample_check_2:
    command: "systemctl is-active sample-service-a"
    parser: systemd_state

  sample_check_3:
    command: "systemctl is-active sample-service-b"
    parser: systemd_state

# ---------------------------------------------------
# 4. 更新（ポーリング）設定
# ---------------------------------------------------
polling:
  interval_seconds: 60      # デフォルト1分（画面から変更可能な初期値）
  auto_refresh: true        # 起動時は自動更新ON

# ---------------------------------------------------
# 5. Web設定
# ---------------------------------------------------
web:
  listen_addr: ":8080"
  auth: none
```

## secrets.yaml（認証情報。Git管理対象外）

`config.yaml`とは別ファイルとし、`.gitignore`に含めてリポジトリにコミットしない。
`config.yaml`側と同じ`environments[].name`をキーとして、環境ごとの`bastion`と
`targets`（`targets[].name`をキー）の認証情報を保持する。

```yaml
environments:
  env-a:
    bastion:
      username: opsuser
      password: "changeme"          # auth_type: password に対応

    targets:
      openshift-cmd-vm:
        username: ocadmin
        private_key_path: keys/env-a/ocadmin.pem

      sample-vm01:
        username: admin
        private_key_path: keys/env-a/admin.pem

      sample-vm02:
        username: admin
        private_key_path: keys/env-a/admin.pem

  env-b:
    bastion:
      username: opsuser-b
      password: "changeme-b"

    targets:
      k8s-cmd-vm:
        username: k8sadmin
        private_key_path: keys/env-b/k8sadmin.pem

      sample-vm01:
        username: admin
        private_key_path: keys/env-b/admin.pem
```

### .gitignore への追加例

```
secrets.yaml
keys/
```

秘密鍵ファイル（`keys/`配下）も併せて除外対象とする。

## 設計のポイント

- **environments（環境）** を最上位の階層とし、その配下に各環境専用の`bastion`と
  `targets`を持たせる。`roles`・`check_definitions`・`polling`・`web`は環境をまたいで
  共通設定として1つだけ持つ（環境ごとにチェック内容を変える必要が生じた場合は
  拡張を検討）。
- サーバアプリは**選択中の環境1つに対してのみSSH接続・ポーリングを行う**。
  Web画面で環境を切り替えた際は、現在の環境への接続を切断し、選択された環境の
  `bastion`に接続し直してから対象サーバのポーリングを再開する。
- **kubernetes**ロールと**openshift**ロールを分けて定義することで、素のKubernetes
  クラスタとOpenShiftクラスタの両方に対応する。`kubernetes`は`kubectl`ベースの
  基本チェック（ノード一覧・Pod一覧）のみ、`openshift`は`oc`ベースの同等チェックに
  加えてOpenShift固有のClusterOperator（`oc get co`）・MachineConfigPool
  （`oc get mcp`）チェックを含む。対象がどちらの環境かに応じて、`targets[].roles`で
  使い分ける。
- **targets（対象サーバ）** と **roles（ロール＝チェック項目の束）** と
  **check_definitions（個々のチェック内容）** の3層構造にすることで、
  「同じ役割のサーバが増えても `targets` に1行追加するだけで済む」ようにしている。
- `targets[].roles` は**配列**とし、1台のVMが複数の役割を兼ねているケースに
  対応する。実行時は該当VMに割り当てられた全roleのチェック項目を
  まとめて（重複除去のうえ）実行する。
- `parser` は取得結果の解析方法を示す識別子。想定しているパーサー種別：
  - `table`：`kubectl get`/`oc get`系のテーブル形式出力をパースして構造化データにする
  - `raw_text`：ステータス確認コマンドの出力のようにそのまま整形表示する
  - `systemd_state`：`active`/`inactive`/`failed`等を正常・異常に対応付ける
  - `json`：JSON形式のAPIレスポンスをパースする（対象サービスが増えた場合用）
- `polling.interval_seconds` はサーバ起動時のデフォルト値。
  Web画面側で一時的に変更・一時停止できる想定（サーバ内部の状態として保持）。
- 認証情報（踏み台パスワード、秘密鍵パス）は`config.yaml`から分離し、
  **`secrets.yaml`に平文で記載**する。`secrets.yaml`と秘密鍵ファイル一式は
  `.gitignore`でリポジトリ管理対象外とし、`config.yaml`は安全にバージョン管理できる
  構成とする。`config.yaml`側の`targets[].name`・`bastion`をキーとして
  `secrets.yaml`側の認証情報と紐付ける。

## フェーズ分け

- **フェーズ1（今回のスコープ）**：各チェックのコマンド実行結果を、加工・判定せずに
  そのまま画面表示する（`raw_text`表示が基本）。`table`パーサーも整形表示目的のみで、
  正常/異常の色分け等は行わない。
- **フェーズ2（今後）**：チェックごとの正常/異常判定ロジックを追加し、
  一覧画面での色分け・アラート表示等を実装する。

## 未確定・要検討事項

- [ ] Pod一覧（`kubectl get pods -A`/`oc get pods -A`）は全Namespace対象だが、
      対象を絞るオプションが必要か
- [ ] 異常判定の閾値（例: OpenShiftの`oc get co`でAvailable=Falseの場合の扱い）→ **フェーズ2で対応**
- [ ] コマンドタイムアウト時間（デフォルト値）
- [ ] 環境切り替え時、切断中の旧環境の接続情報（SSHトンネル等）を即座に破棄するか、
      一定時間キャッシュして再切り替え時に素早く再接続できるようにするか
