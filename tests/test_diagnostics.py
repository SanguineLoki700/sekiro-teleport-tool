from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from connection_diagnostics import (PROCESS_RIGHTS, ConnectionIssue, classify_failure,
                                    diagnostic_text, open_process_handle)
from teleport_core import GameUnavailable


@pytest.mark.parametrize("exception,reason,state", [
    (type("ProcessNotFound", (Exception,), {})("sekiro.exe"), "game_not_found", "waiting"),
    (PermissionError("denied"), "access_denied", "error"),
    (ConnectionIssue("open_failed", "gone", winerror=87), "open_failed", "error"),
    (GameUnavailable("null player"), "player_unavailable", "waiting"),
    (ConnectionIssue("module_pending", "starting"), "module_pending", "waiting"),
    (ImportError("pymem"), "missing_dependency", "error"),
    (RuntimeError("unknown"), "unexpected_error", "error"),
])
def test_connection_reasons_remain_distinct(exception, reason, state):
    info = classify_failure(exception)
    assert info["reason"] == reason
    assert info["state"] == state
    assert info["advice"]
    assert "unsupported" not in info["message"].lower()


def test_process_open_uses_required_rights_without_full_access():
    kernel = SimpleNamespace(OpenProcess=Mock(return_value=1234))
    with patch("connection_diagnostics.ctypes.WinDLL", return_value=kernel):
        assert open_process_handle(55) == 1234
    requested, inherit, pid = kernel.OpenProcess.call_args.args
    assert requested == PROCESS_RIGHTS
    assert requested & 0x38 == 0x38  # Coordinate read/write/VM operation.
    assert not requested & (0x1 | 0x2 | 0x800)  # No terminate/create-thread/suspend.
    assert inherit is False and pid == 55


def test_open_denial_retains_windows_error_and_process_id():
    kernel = SimpleNamespace(OpenProcess=Mock(return_value=0))
    with patch("connection_diagnostics.ctypes.WinDLL", return_value=kernel), patch("connection_diagnostics.ctypes.get_last_error", return_value=5):
        with pytest.raises(ConnectionIssue) as failure:
            open_process_handle(55)
    info = classify_failure(failure.value)
    assert info["reason"] == "access_denied"
    assert info["winerror"] == 5 and info["pid"] == 55
    assert info["stage"] == "open_process"


def test_help_gives_relevant_next_step_and_does_not_ask_to_move_save(tmp_path):
    report = {"connection": classify_failure(GameUnavailable("null player")),
              "game": {"version": "1.6.0.0", "pid": 123}}
    text = diagnostic_text(report, tmp_path, "portable")
    assert "already playing" in text
    assert "1.6.0.0" in text
    assert "There is no need to move it" in text
    assert "Beside the tool" in text
