"""チェックのバックグラウンド定期実行と結果キャッシュを担当するモジュール（Issue #17）。

以前は/api/statusリクエストのたびにその場でSSH接続〜全チェックを同期実行して
いたが、この方式には次の問題があった。

- SSH多段接続＋全チェックは数十秒かかりうるため、画面の応答が遅い
- ブラウザのタブを複数開くと、タブ数分のSSH接続・チェックがまるごと走る
- ポーリングが実行時間と重なると多重実行される
- waitressのワーカースレッドを長時間占有する

そのため、チェックは専用のバックグラウンドスレッド1本だけが実行する方式に
変更した。スレッドは設定間隔で定期実行（自動更新OFF時は手動トリガー待ち）し、
結果と実行時刻をメモリにキャッシュする。/api/statusはキャッシュを即時返す
だけなので、何タブ開いても・どれだけ頻繁にポーリングしてもSSH接続は増えない。
実行スレッドが1本であることが「多重起動しない」ことの保証になっている。

環境切り替え時はキャッシュを破棄して新環境での実行を予約する。切り替えの
瞬間に旧環境のチェックが実行中だった場合、その結果は完了後に破棄する
（旧環境の結果を新環境の結果として表示しないため）。
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime

from app.checker import _stage, run_checks
from app.config import Config, Secrets

logger = logging.getLogger(__name__)


class StatusPoller:
    """チェックを定期実行するバックグラウンドスレッドと、その結果キャッシュ。"""

    def __init__(self, cfg: Config, secrets: Secrets, env_name: str) -> None:
        self._cfg = cfg
        self._secrets = secrets

        self._lock = threading.Lock()
        # 設定変更・手動更新の際に、スレッドの待機を中断して即座に反応させるためのイベント
        self._wakeup = threading.Event()

        self._env_name = env_name
        self._interval_seconds = cfg.polling.interval_seconds
        self._auto_refresh = cfg.polling.auto_refresh

        self._result: dict | None = None
        self._checked_at: str | None = None
        self._running = False
        # Trueにするとスレッドが次の周回でチェックを実行する（起動直後は
        # 自動更新OFFでも初回の結果を表示できるよう、最初から予約しておく）
        self._refresh_requested = True

        self._thread = threading.Thread(target=self._loop, name="status-poller", daemon=True)

    def start(self) -> None:
        """バックグラウンドスレッドを開始する。"""
        self._thread.start()

    def snapshot(self) -> dict:
        """現在の状態（キャッシュ済み結果・実行時刻・実行中フラグ・設定）を返す。"""
        with self._lock:
            return {
                "result": self._result,
                "checked_at": self._checked_at,
                "running": self._running,
                "current_environment": self._env_name,
                "polling": {
                    "interval_seconds": self._interval_seconds,
                    "auto_refresh": self._auto_refresh,
                },
            }

    def trigger_refresh(self) -> None:
        """手動更新。実行中の場合は何もしない（直後に新しい結果が出るため）。"""
        with self._lock:
            if self._running:
                return
            self._refresh_requested = True
        self._wakeup.set()

    def set_environment(self, name: str) -> None:
        """環境を切り替え、キャッシュを破棄して新環境でのチェック実行を予約する。"""
        with self._lock:
            self._env_name = name
            self._result = None
            self._checked_at = None
            self._refresh_requested = True
        self._wakeup.set()

    def update_polling(self, interval_seconds: int | None = None, auto_refresh: bool | None = None) -> None:
        """更新間隔・自動更新ON/OFFを変更する。待機中のスレッドに即座に反映される。"""
        with self._lock:
            if interval_seconds is not None:
                self._interval_seconds = interval_seconds
            if auto_refresh is not None:
                self._auto_refresh = auto_refresh
        self._wakeup.set()

    def _loop(self) -> None:
        while True:
            with self._lock:
                due = self._refresh_requested or self._auto_refresh
                self._refresh_requested = False
                env_name = self._env_name
                if due:
                    self._running = True

            if due:
                result = self._run_once(env_name)
                with self._lock:
                    self._running = False
                    # 実行中に環境が切り替わっていた場合、旧環境の結果は破棄する
                    if env_name == self._env_name:
                        self._result = result
                        self._checked_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            with self._lock:
                timeout = self._interval_seconds if self._auto_refresh else None
            # 自動更新ONなら間隔経過まで、OFFなら手動トリガー・設定変更まで待つ
            if self._wakeup.wait(timeout=timeout):
                self._wakeup.clear()

    def _run_once(self, env_name: str) -> dict:
        """1回分のチェックを実行する。

        想定内の接続・実行エラーはrun_checks内で結果に変換されるため、ここで
        例外が来るのはプログラムのバグ等の想定外のみ。以前はFlaskの500エラーに
        なっていたが、バックグラウンドスレッドでは例外を放置するとスレッドが
        死んで以降の更新が止まってしまうため、捕捉して結果として画面に出す。
        """
        try:
            return run_checks(self._cfg, self._secrets, env_name=env_name)
        except Exception as e:  # noqa: BLE001
            logger.exception("環境「%s」のチェック実行中に予期しないエラーが発生しました", env_name)
            return {
                "environment": env_name,
                "stages": {
                    "internal_error": _stage(False, f"チェック実行中に予期しないエラーが発生しました: {e}"),
                },
                "targets": [],
            }
