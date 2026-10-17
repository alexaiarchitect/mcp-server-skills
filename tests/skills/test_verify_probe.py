"""`probe.py` against the in-process fake MCP server, in each of its shapes."""

from __future__ import annotations

from mcp_server_skills.report import EXIT_FINDINGS, EXIT_INCONCLUSIVE, EXIT_OK, EXIT_USAGE

PROBE = "skills/mcp-verify/scripts/probe.py"


def probe(run_script, url, *args):
    return run_script(PROBE, url, "--json", "--n", "3", "--timeout", "5", *args)


def test_a_dual_server_passes_every_check(run_script, fake_server):
    result = probe(run_script, fake_server("dual"), "--legacy")
    assert result.returncode == EXIT_OK, result.stdout
    data = result.json()
    assert data["discovered"]["era"] == "dual"
    assert data["findings"] == []
    checks = {c["check"]: c["ok"] for c in data["discovered"]["checks"]}
    assert checks["Mcp-Method mismatch"] and checks["Mcp-Method missing"] and checks["legacy initialize"]
    latency = data["discovered"]["latency"]
    assert set(latency) == {"server/discover", "tools/list", "initialize (legacy)", "tools/list (legacy)"}
    assert latency["tools/list"]["n"] == 2 + 3
    assert data["discovered"]["tools"] == 2


def test_a_legacy_only_server_is_handshake(run_script, fake_server):
    result = probe(run_script, fake_server("legacy"), "--legacy")
    assert result.returncode == EXIT_FINDINGS
    assert result.json()["discovered"]["era"] == "handshake"
    assert result.ids() == {"PRB010"}


def test_a_modern_only_server_refuses_legacy(run_script, fake_server):
    result = probe(run_script, fake_server("modern"), "--legacy")
    assert result.json()["discovered"]["era"] == "stateless"
    assert "PRB012" in result.ids()


def test_a_lax_server_fails_headers_results_and_cache(run_script, fake_server):
    result = probe(run_script, fake_server("lax"))
    assert {"PRB020", "PRB021", "PRB030", "PRB031", "PRB032"} <= result.ids()
    assert result.returncode == EXIT_FINDINGS


def test_the_latency_budget(run_script, fake_server):
    url = fake_server("dual", delay=0.03)
    generic = probe(run_script, url, "--budget-ms", "10")
    assert "PRB050" in generic.ids() and generic.returncode == EXIT_OK, "a warning by default"
    alexa = probe(run_script, url, "--budget-ms", "10", "--profile", "alexa")
    assert alexa.returncode == EXIT_FINDINGS
    assert next(f for f in alexa.json()["findings"] if f["id"] == "PRB050")["severity"] == "error"
    assert alexa.json()["discovered"]["era"] == "dual", "the alexa profile implies --legacy"
    relaxed = probe(run_script, url, "--budget-ms", "5000", "--profile", "alexa")
    assert "PRB050" not in relaxed.ids()


def test_auth_required_with_and_without_a_token(run_script, fake_server):
    url = fake_server("dual", token="s3cret")
    without = probe(run_script, url)
    assert without.returncode == EXIT_INCONCLUSIVE
    assert without.json()["discovered"]["auth"]["prm_ok"] is True
    assert run_script(PROBE, url, "--token-env", "PROBE_TOKEN", env={"PROBE_TOKEN": ""}).returncode == EXIT_USAGE
    with_token = run_script(PROBE, url, "--json", "--n", "2", "--token-env", "PROBE_TOKEN", "--legacy",
                            env={"PROBE_TOKEN": "s3cret"})
    assert with_token.returncode == EXIT_OK, with_token.stdout
    auth = with_token.json()["discovered"]["auth"]
    assert auth["unauthenticated_status"] == 401 and auth["www_authenticate"] is True
    assert "s3cret" not in with_token.stdout


def test_a_401_without_a_challenge_is_reported(run_script, fake_server):
    url = fake_server("dual", token="t", challenge=False)
    result = run_script(PROBE, url, "--json", "--n", "1", "--token-env", "T", env={"T": "t"})
    assert "PRB041" in result.ids()
    assert result.json()["discovered"]["auth"]["prm_ok"] is True, "falls back to the well-known path"


def test_unreachable_and_bad_arguments(run_script):
    assert run_script(PROBE, "http://127.0.0.1:9/mcp", "--json", "--timeout", "2").returncode == EXIT_USAGE
    assert run_script(PROBE, "ftp://x").returncode == EXIT_USAGE
    assert run_script(PROBE, "http://127.0.0.1:9/mcp", "--token-env", "DEFINITELY_UNSET_VAR_X").returncode == EXIT_USAGE


def test_markdown_shows_checks_and_latency(run_script, fake_server):
    out = run_script(PROBE, fake_server("dual"), "--n", "2", "--legacy").stdout
    assert "## Found" in out and "p95_ms" in out and "era**: dual" in out
