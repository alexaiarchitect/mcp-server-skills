"""Shared test fixtures.

The plugin's library is stdlib-only, so tests import it directly. Scripts are
exercised as subprocesses, the way a skill runs them, so argument parsing and
exit codes are covered too. Live checks run against the in-process fake MCP
server in `fixtures/servers/fake_mcp.py` on 127.0.0.1, so nothing needs the
network or a credential.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

# Keep the plugin tree clean while testing, as the scripts do (F03).
sys.dont_write_bytecode = True

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
LIB = PLUGIN_ROOT / "lib"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

sys.path.insert(0, str(LIB))
sys.path.insert(0, str(FIXTURES / "servers"))


@dataclass
class ScriptRun:
    returncode: int
    stdout: str
    stderr: str

    def json(self) -> dict:
        return json.loads(self.stdout)

    def ids(self) -> set[str]:
        return {f["id"] for f in self.json()["findings"]}

    @property
    def combined(self) -> str:
        return f"{self.stdout}\n{self.stderr}"


@pytest.fixture(scope="session")
def plugin_root() -> Path:
    return PLUGIN_ROOT


@pytest.fixture(scope="session")
def fixtures() -> Path:
    return FIXTURES


@pytest.fixture
def run_script():
    """Run a plugin script by its path relative to the plugin root."""

    def _run(relative: str, *args: str, cwd: Path | str | None = None,
             env: dict[str, str] | None = None, timeout: int = 120) -> ScriptRun:
        script = PLUGIN_ROOT / relative
        assert script.is_file(), f"no such script: {script}"
        merged = {**os.environ, **(env or {})}
        proc = subprocess.run([sys.executable, str(script), *[str(a) for a in args]],
                              capture_output=True, text=True, cwd=str(cwd) if cwd else None,
                              timeout=timeout, env=merged)
        return ScriptRun(proc.returncode, proc.stdout, proc.stderr)

    return _run


@pytest.fixture
def project(fixtures: Path):
    """A fixture project by name, e.g. `project("ts_v1_lambda")` (read-only)."""

    def _get(name: str) -> Path:
        path = fixtures / "projects" / name
        assert path.is_dir(), f"no such fixture project: {path}"
        return path

    return _get


@pytest.fixture
def tmp_project(tmp_path: Path, fixtures: Path):
    """A writable copy of a fixture project, for tests that write."""

    def _copy(name: str) -> Path:
        target = tmp_path / name
        shutil.copytree(fixtures / "projects" / name, target)
        return target

    return _copy


@pytest.fixture
def fake_server():
    """Start the fake MCP server; every server started is shut down after the test."""
    import fake_mcp

    started = []

    def _start(mode: str = "dual", **kwargs) -> str:
        server, url = fake_mcp.serve(mode, **kwargs)
        started.append(server)
        return url

    yield _start
    for server in started:
        server.shutdown()
        server.server_close()
