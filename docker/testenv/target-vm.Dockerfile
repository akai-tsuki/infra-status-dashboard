# M2検証用のダミーコマンド(kubectl/oc/sample-status-command)を焼き込んだ
# 対象VMイメージ。本番アプリのイメージ(リポジトリルートのDockerfile)とは
# 無関係で、テスト用踏み台・対象VM環境（docker-compose.yml）専用。
FROM lscr.io/linuxserver/openssh-server

COPY dummy-bin/kubectl /usr/local/bin/kubectl
COPY dummy-bin/oc /usr/local/bin/oc
COPY dummy-bin/sample-status-command /usr/local/bin/sample-status-command
RUN chmod +x /usr/local/bin/kubectl /usr/local/bin/oc /usr/local/bin/sample-status-command
