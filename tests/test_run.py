"""run.py のユニットテスト（Issue #22）。resolve_listen_addr()の変換ロジックのみを対象にする。"""

import pytest

from run import resolve_listen_addr


@pytest.mark.parametrize(
    "listen_addr, expected",
    [
        (":18080", ("0.0.0.0", 18080)),
        (":8080", ("0.0.0.0", 8080)),
        ("127.0.0.1:8080", ("127.0.0.1", 8080)),
        ("0.0.0.0:18080", ("0.0.0.0", 18080)),
        ("bastion.example.local:22", ("bastion.example.local", 22)),
    ],
)
def test_resolve_listen_addr(listen_addr, expected):
    assert resolve_listen_addr(listen_addr) == expected
