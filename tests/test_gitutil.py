"""Unit tests for gitutil.resolve_branch_head (git ls-remote wrapper)."""

import subprocess
from unittest.mock import patch

import pytest

from orbital.gitutil import GitError, resolve_branch_head


def _completed(stdout: str) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


def test_resolve_branch_head_returns_sha():
    out = "aaa111\trefs/heads/main\nbbb222\trefs/heads/dev\n"
    with patch("subprocess.run", return_value=_completed(out)) as mock_run:
        sha = resolve_branch_head("https://github.com/x/y", "main")
    assert sha == "aaa111"
    args, kwargs = mock_run.call_args
    assert args[0] == ["git", "ls-remote", "https://github.com/x/y", "refs/heads/main"]
    assert kwargs["timeout"] == 30


def test_resolve_branch_head_picks_matching_ref_only():
    out = "ccc333\trefs/heads/main-old\nddd444\trefs/heads/dev\neee555\trefs/heads/main\n"
    with patch("subprocess.run", return_value=_completed(out)):
        assert resolve_branch_head("https://github.com/x/y", "main") == "eee555"


def test_resolve_branch_head_custom_timeout():
    with patch("subprocess.run", return_value=_completed("")) as mock_run:
        with pytest.raises(GitError, match="not found"):
            resolve_branch_head("https://github.com/x/y", "main", timeout=5)
    assert mock_run.call_args.kwargs["timeout"] == 5


def test_resolve_branch_head_branch_not_found():
    out = "aaa111\trefs/heads/dev\n"
    with patch("subprocess.run", return_value=_completed(out)):
        with pytest.raises(GitError, match="branch 'main' not found"):
            resolve_branch_head("https://github.com/x/y", "main")


def test_resolve_branch_head_empty_output_not_found():
    with patch("subprocess.run", return_value=_completed("")):
        with pytest.raises(GitError, match="not found"):
            resolve_branch_head("https://github.com/x/y", "main")


def test_resolve_branch_head_process_error_wrapped():
    err = subprocess.CalledProcessError(128, ["git"], output="", stderr="fatal: repo not found\n")
    with patch("subprocess.run", side_effect=err):
        with pytest.raises(GitError, match="git ls-remote failed: fatal: repo not found"):
            resolve_branch_head("https://github.com/x/y", "main")


def test_resolve_branch_head_timeout_wrapped():
    exc = subprocess.TimeoutExpired(cmd=["git"], timeout=30)
    with patch("subprocess.run", side_effect=exc):
        with pytest.raises(GitError, match="timed out"):
            resolve_branch_head("https://github.com/x/y", "main")
