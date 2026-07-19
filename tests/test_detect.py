"""Tests for the dependency-detection script (SPEC §4.3) run against fixture repos."""

import subprocess
from pathlib import Path

import pytest

from streamlit_host.k8s.scripts import DETECT_SH

BASE = "registry.test:80/streamlit-base:py3.12"


def run_detect(src: Path, main_file: str = "streamlit_app.py"):
    script = src.parent / "detect.sh"
    script.write_text(DETECT_SH)
    return subprocess.run(
        ["sh", str(script)],
        env={
            "PATH": "/usr/bin:/bin",
            "SRC_DIR": str(src),
            "MAIN_FILE": main_file,
            "BASE_IMAGE": BASE,
        },
        capture_output=True,
        text=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    (src / "streamlit_app.py").write_text("import streamlit as st\n")
    return src


def dockerfile(src: Path) -> str:
    return (src / "Dockerfile.streamlit-host").read_text()


def test_requirements_txt(repo: Path):
    (repo / "requirements.txt").write_text("pandas\n")
    r = run_detect(repo)
    assert r.returncode == 0, r.stderr
    df = dockerfile(repo)
    assert f"FROM {BASE}" in df
    assert "uv pip install --system -r /tmp/deps/requirements.txt" in df
    assert 'CMD ["streamlit", "run", "streamlit_app.py"' in df
    assert "--client.showErrorDetails=false" in df


def test_uv_lock_takes_priority(repo: Path):
    (repo / "requirements.txt").write_text("pandas\n")
    (repo / "uv.lock").write_text("")
    (repo / "pyproject.toml").write_text("[project]\nname='x'\nversion='0'\n")
    r = run_detect(repo)
    assert r.returncode == 0, r.stderr
    assert "uv export --frozen" in dockerfile(repo)


def test_pyproject_fallback(repo: Path):
    (repo / "pyproject.toml").write_text("[project]\nname='x'\nversion='0'\n")
    r = run_detect(repo)
    assert r.returncode == 0, r.stderr
    assert "uv pip compile pyproject.toml" in dockerfile(repo)


def test_entrypoint_dir_searched_first(repo: Path):
    sub = repo / "sub"
    sub.mkdir()
    (sub / "app.py").write_text("import streamlit\n")
    (sub / "requirements.txt").write_text("numpy\n")
    (repo / "requirements.txt").write_text("pandas\n")
    r = run_detect(repo, main_file="sub/app.py")
    assert r.returncode == 0, r.stderr
    assert "COPY sub/requirements.txt" in dockerfile(repo)


def test_packages_txt_warns_but_builds(repo: Path):
    (repo / "requirements.txt").write_text("pandas\n")
    (repo / "packages.txt").write_text("libmysqlclient-dev\n")
    r = run_detect(repo)
    assert r.returncode == 0, r.stderr
    assert "NOT supported" in r.stdout


def test_pipfile_alone_fails(repo: Path):
    (repo / "Pipfile").write_text("")
    r = run_detect(repo)
    assert r.returncode == 1
    assert "not supported" in r.stdout


def test_no_deps_warns(repo: Path):
    r = run_detect(repo)
    assert r.returncode == 0, r.stderr
    assert "no dependency file found" in r.stdout
    assert f"FROM {BASE}" in dockerfile(repo)


def test_missing_main_file_fails(repo: Path):
    r = run_detect(repo, main_file="nope.py")
    assert r.returncode == 1
    assert "not found" in r.stdout
