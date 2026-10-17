"""Conventions that hold across the whole plugin.

These stop the plugin drifting as it grows: every skill has a usable
description, the confirm step's tool and its own scripts; every reference
cites its sources; every script answers `--help` and `--json`, and every
script that writes answers `--dry-run`; every linked file and named script
exists; no third-party package is imported; the README lists every skill;
and every finding id the code can emit is documented in
`skills/mcp-server/references/findings.md`, and nothing documented is
missing from the catalog.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SKILLS = sorted(p for p in (PLUGIN_ROOT / "skills").iterdir() if p.is_dir())
SKILL_FILES = [p / "SKILL.md" for p in SKILLS]
REFERENCES = sorted((PLUGIN_ROOT / "skills").rglob("references/*.md"))
SCRIPTS = sorted(p for p in (PLUGIN_ROOT / "skills").rglob("scripts/*.py") if not p.name.startswith("_"))
LIB_MODULES = sorted((PLUGIN_ROOT / "lib" / "mcp_server_skills").glob("*.py"))
FINDINGS_DOC = PLUGIN_ROOT / "skills" / "mcp-server" / "references" / "findings.md"

EXPECTED_SKILLS = {
    "mcp-server", "mcp-discover", "mcp-review", "mcp-migrate", "mcp-verify",
    "mcp-auth", "mcp-alexa", "mcp-ci", "mcp-upgrade",
}
#: Scripts that write files; each must offer --dry-run.
WRITERS = {"plan_migration.py", "apply_codemod.py", "tools_lock.py", "friction_log.py",
           "gen_workflow.py", "check_spec.py"}
ID_PATTERN = re.compile(r"\b(?:DSC|MCP|AUT|ALX|PRB|MIG|CI|UPG)\d{3}\b")


def frontmatter(path: Path) -> dict[str, str]:
    sys.path.insert(0, str(PLUGIN_ROOT / "lib"))
    from mcp_server_skills.frontmatter import read

    return read(str(path)).meta


# -- structure -------------------------------------------------------------

def test_the_expected_skills_are_all_present():
    assert {p.name for p in SKILLS} == EXPECTED_SKILLS


def test_the_plugin_manifest_is_valid():
    manifest = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert manifest["name"] == "mcp-server"
    assert re.match(r"^\d+\.\d+\.\d+$", manifest["version"])
    assert manifest["license"] == "Apache-2.0"
    assert manifest["author"]["email"] == "alex@alexaiarchitect.com"
    assert manifest["repository"] == "https://github.com/alexaiarchitect/mcp-server-skills"
    assert manifest["experimental"]["evals"] == "plugin-evals"


def test_the_marketplace_manifest_names_this_plugin():
    marketplace = json.loads((PLUGIN_ROOT / ".claude-plugin" / "marketplace.json").read_text())
    assert marketplace["name"] == "alexaiarchitect-mcp-server"
    assert [p["name"] for p in marketplace["plugins"]] == ["mcp-server"]


def test_licensing_files_are_present():
    license_text = (PLUGIN_ROOT / "LICENSE").read_text()
    assert "Apache License" in license_text and "Version 2.0" in license_text
    notices = (PLUGIN_ROOT / "THIRD_PARTY_NOTICES.md").read_text()
    for project in ("typescript-sdk", "python-sdk", "modelcontextprotocol.io", "developer.amazon.com"):
        assert project in notices


def test_the_readme_lists_every_skill_and_the_install_commands():
    readme = (PLUGIN_ROOT / "README.md").read_text()
    for skill in EXPECTED_SKILLS:
        assert f"/mcp-server:{skill}" in readme, f"README does not list {skill}"
    assert "/plugin marketplace add alexaiarchitect/mcp-server-skills" in readme
    assert "/plugin install mcp-server@alexaiarchitect-mcp-server" in readme


def test_the_version_is_the_same_everywhere():
    sys.path.insert(0, str(PLUGIN_ROOT / "lib"))
    from mcp_server_skills import __version__

    manifest = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text())
    pyproject = (PLUGIN_ROOT / "pyproject.toml").read_text()
    assert manifest["version"] == __version__
    assert f'version = "{__version__}"' in pyproject


# -- SKILL.md --------------------------------------------------------------

@pytest.mark.parametrize("skill", SKILL_FILES, ids=lambda p: p.parent.name)
def test_every_skill_has_valid_frontmatter_named_after_its_directory(skill):
    meta = frontmatter(skill)
    assert meta["name"] == skill.parent.name
    assert set(meta) >= {"name", "description", "argument-hint", "allowed-tools"}


@pytest.mark.parametrize("skill", SKILL_FILES, ids=lambda p: p.parent.name)
def test_every_description_says_when_to_use_and_when_not_to(skill):
    description = frontmatter(skill)["description"]
    assert len(description) > 200, "too short to route on"
    assert "Use when" in description
    assert "Don't use" in description


@pytest.mark.parametrize("skill", SKILL_FILES, ids=lambda p: p.parent.name)
def test_every_skill_declares_the_tools_it_needs(skill):
    tools = frontmatter(skill)["allowed-tools"]
    assert "AskUserQuestion" in tools, "the confirm step needs it"
    assert "Bash(python3 *)" in tools, "every skill runs its own scripts"


@pytest.mark.parametrize("skill", SKILL_FILES, ids=lambda p: p.parent.name)
def test_no_skill_forks_its_context(skill):
    assert "context" not in frontmatter(skill)


@pytest.mark.parametrize("skill", SKILL_FILES, ids=lambda p: p.parent.name)
def test_skill_bodies_stay_short_enough_to_load(skill):
    lines = skill.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 200, f"{len(lines)} lines; move detail into references/"


@pytest.mark.parametrize("skill", SKILL_FILES, ids=lambda p: p.parent.name)
def test_every_skill_follows_the_five_steps(skill):
    text = skill.read_text(encoding="utf-8")
    assert "## Completion checklist" in text
    assert "AskUserQuestion" in text.split("---", 2)[2], "the body must say where it confirms"
    assert "${CLAUDE_SKILL_DIR}" in text


@pytest.mark.parametrize("skill", SKILL_FILES, ids=lambda p: p.parent.name)
def test_every_linked_reference_exists(skill):
    text = skill.read_text(encoding="utf-8")
    for link in re.findall(r"\]\((references/[^)#]+)", text):
        assert (skill.parent / link).is_file(), f"{skill.parent.name}: dead link to {link}"


@pytest.mark.parametrize("skill", SKILL_FILES, ids=lambda p: p.parent.name)
def test_every_script_a_skill_names_exists(skill):
    text = skill.read_text(encoding="utf-8")
    for match in re.findall(r"(?:\$\{CLAUDE_SKILL_DIR\}/|`)(scripts/[a-z_]+\.py)", text):
        assert (skill.parent / match).is_file(), f"{skill.parent.name}: names a missing {match}"


CROSS_SKILL = re.compile(r"\$\{CLAUDE_SKILL_DIR\}/\.\./([a-z-]+)/((?:scripts|references)/[a-z_\-]+\.(?:py|md))")


@pytest.mark.parametrize("document", SKILL_FILES + REFERENCES, ids=lambda p: f"{p.parent.parent.name}/{p.name}")
def test_every_cross_skill_path_exists(document):
    text = document.read_text(encoding="utf-8")
    for other, rel in CROSS_SKILL.findall(text):
        target = PLUGIN_ROOT / "skills" / other / rel
        assert target.is_file(), f"{document.name}: names a missing {other}/{rel}"


BARE_SKILL_DIR = re.compile(r"(?<!\{CLAUDE_)\bSKILL_DIR\b")


@pytest.mark.parametrize("document", SKILL_FILES + REFERENCES, ids=lambda p: f"{p.parent.parent.name}/{p.name}")
def test_no_bare_skill_dir_placeholder_survives(document):
    offenders = [l for l in document.read_text(encoding="utf-8").splitlines() if BARE_SKILL_DIR.search(l)]
    assert offenders == []


# -- references ------------------------------------------------------------

@pytest.mark.parametrize("reference", REFERENCES, ids=lambda p: f"{p.parent.parent.name}/{p.name}")
def test_every_reference_cites_its_sources(reference):
    text = reference.read_text(encoding="utf-8")
    assert "Sources:" in text, "add a Sources: footer"
    assert text.rstrip().endswith((".", ")", "`")), "the footer looks truncated"


@pytest.mark.parametrize("reference", REFERENCES, ids=lambda p: f"{p.parent.parent.name}/{p.name}")
def test_references_are_substantial_but_not_sprawling(reference):
    lines = reference.read_text(encoding="utf-8").splitlines()
    assert 25 <= len(lines) <= 250, f"{len(lines)} lines"


# -- scripts ---------------------------------------------------------------

@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: f"{p.parent.parent.name}/{p.name}")
def test_every_script_has_help_and_a_docstring(script):
    result = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert len(result.stdout) > 300, "the help text should explain why, not just how"
    assert script.read_text(encoding="utf-8").split("\n", 1)[1].lstrip().startswith('"""')


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: f"{p.parent.parent.name}/{p.name}")
def test_every_script_speaks_json(script):
    result = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True, timeout=60)
    assert "--json" in result.stdout


@pytest.mark.parametrize("script", [s for s in SCRIPTS if s.name in WRITERS], ids=lambda p: p.name)
def test_every_writer_has_a_dry_run(script):
    result = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True, timeout=60)
    assert "--dry-run" in result.stdout


def test_the_writer_list_is_complete():
    """A script that opens a file for writing must be on the WRITERS list."""
    for script in SCRIPTS:
        code = code_outside_strings(script)
        if re.search(r"\.write_text\s*\(|open\s*\([^)]*['\"]w", code) and script.name not in WRITERS:
            pytest.fail(f"{script.name} writes files but is not in WRITERS")


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: f"{p.parent.parent.name}/{p.name}")
def test_every_script_finds_the_shared_library_the_same_way(script):
    assert 'parents[3] / "lib"' in script.read_text(encoding="utf-8")


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: f"{p.parent.parent.name}/{p.name}")
def test_every_script_compiles_for_python_3_10(script):
    import ast

    ast.parse(script.read_text(encoding="utf-8"), feature_version=(3, 10))


def code_outside_strings(path: Path) -> str:
    """The module's source with string literals and comments blanked out."""
    import io
    import tokenize

    source = path.read_text(encoding="utf-8")
    dropped = {tokenize.STRING, tokenize.COMMENT}
    for name in ("FSTRING_START", "FSTRING_MIDDLE", "FSTRING_END"):
        if hasattr(tokenize, name):
            dropped.add(getattr(tokenize, name))
    kept = [tok.string for tok in tokenize.generate_tokens(io.StringIO(source).readline) if tok.type not in dropped]
    return " ".join(kept)


STDLIB = set(getattr(sys, "stdlib_module_names", ())) | {"__future__"}


def imported_top_level(path: Path) -> set[str]:
    import ast

    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


@pytest.mark.parametrize("module", SCRIPTS + LIB_MODULES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_no_third_party_imports(module):
    """Everything runs on a bare interpreter, before the project's environment works."""
    if not STDLIB:
        pytest.skip("sys.stdlib_module_names needs Python 3.10+")
    foreign = imported_top_level(module) - STDLIB - {"mcp_server_skills"}
    assert foreign == set(), f"{module.name} imports {foreign}"


@pytest.mark.parametrize("module", LIB_MODULES, ids=lambda p: p.name)
def test_every_library_module_explains_itself(module):
    assert module.read_text(encoding="utf-8").lstrip().startswith('"""')


def test_the_readers_never_execute_project_code():
    for name in ("ts_scan.py", "py_scan.py", "layout.py", "inventory.py"):
        code = code_outside_strings(PLUGIN_ROOT / "lib" / "mcp_server_skills" / name)
        for banned in ("exec (", "eval (", "importlib", "__import__", "subprocess"):
            assert banned not in code, f"{name} uses {banned}"


# -- findings --------------------------------------------------------------

def _catalog():
    sys.path.insert(0, str(PLUGIN_ROOT / "lib"))
    from mcp_server_skills.catalog import CATALOG

    return CATALOG


def test_every_catalog_id_is_documented_and_vice_versa():
    documented = set(re.findall(r"^\| `([A-Z]+\d{3})` \|", FINDINGS_DOC.read_text(encoding="utf-8"), re.M))
    assert documented == set(_catalog()), {
        "undocumented": sorted(set(_catalog()) - documented),
        "documented but not in the catalog": sorted(documented - set(_catalog())),
    }


def test_the_documented_severity_matches_the_catalog():
    rows = re.findall(r"^\| `([A-Z]+\d{3})` \| (\w+) \|", FINDINGS_DOC.read_text(encoding="utf-8"), re.M)
    catalog = _catalog()
    for fid, severity in rows:
        assert catalog[fid].severity == severity, fid


def test_every_id_the_code_emits_is_in_the_catalog():
    catalog = set(_catalog())
    emitted: set[str] = set()
    for path in SCRIPTS + [m for m in LIB_MODULES if m.name != "catalog.py"]:
        emitted |= set(ID_PATTERN.findall(path.read_text(encoding="utf-8")))
    missing = emitted - catalog
    assert missing == set(), f"emitted but not catalogued: {sorted(missing)}"


def test_every_id_a_reference_mentions_exists():
    catalog = set(_catalog())
    for doc in REFERENCES + SKILL_FILES:
        unknown = set(ID_PATTERN.findall(doc.read_text(encoding="utf-8"))) - catalog
        assert unknown == set(), f"{doc.relative_to(PLUGIN_ROOT)} mentions {sorted(unknown)}"


def test_every_catalog_entry_has_a_fix_and_an_https_source():
    for entry in _catalog().values():
        assert entry.fix and entry.title
        assert entry.source.startswith("https://"), entry.id
        assert entry.severity in ("error", "warn", "info")


# -- evals -----------------------------------------------------------------

def test_plugin_evals_have_the_expected_grammar():
    evals = PLUGIN_ROOT / "plugin-evals"
    cases = sorted(p for p in evals.iterdir() if p.is_dir() and p.name != "results")
    assert len(cases) >= 8
    for case in cases:
        assert (case / "case.yaml").is_file(), case.name
        assert (case / "prompt.md").is_file(), case.name
        graders = list((case / "graders").glob("*.md"))
        assert graders, case.name
        assert "skill-fired.md" in {g.name for g in graders}, case.name
        assert f"name: {case.name}" in (case / "case.yaml").read_text()


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: f"{p.parent.parent.name}/{p.name}")
def test_every_script_leaves_no_bytecode_behind(script):
    """A read-only install must stay clean: no __pycache__ under skills/ or lib/ (friction F03)."""
    text = script.read_text(encoding="utf-8")
    assert "sys.dont_write_bytecode = True" in text
    assert text.index("sys.dont_write_bytecode = True") < text.index('parents[3] / "lib"')
