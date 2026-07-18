"""アプリケーションの実行時状態（現在選択中の環境）を保持するモジュール。

Flask + waitressはリクエストごとに複数スレッドで動作しうるため、
現在の環境名の読み書きをロックで保護する。
"""

import threading


class AppState:
    def __init__(self, default_env_name: str) -> None:
        self._lock = threading.Lock()
        self._current_env_name = default_env_name

    @property
    def current_env_name(self) -> str:
        with self._lock:
            return self._current_env_name

    def set_current_env_name(self, name: str) -> None:
        with self._lock:
            self._current_env_name = name
